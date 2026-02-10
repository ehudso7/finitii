"""Bill service: derived views over RecurringPattern.

Bills & Subscriptions are NOT separate models — they are views over
RecurringPattern with user-facing semantics:
- List all bills (active recurring patterns) with confidence visible
- Create manual bills (is_manual=True) that feed into forecast + STS
- Toggle essential flag (suppresses cancellation recommendations)
- Update and deactivate bills

All actions audit-logged. No automation or negotiation.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.services import audit_service


async def get_bills(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[RecurringPattern]:
    """Get all active bills/subscriptions for a user.

    Bills are a derived view over RecurringPattern.
    Confidence is always visible on every returned bill.
    """
    result = await db.execute(
        select(RecurringPattern)
        .where(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active == True,  # noqa: E712
        )
        .order_by(RecurringPattern.estimated_amount.desc())
    )
    return list(result.scalars().all())


async def get_bill(
    db: AsyncSession,
    bill_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RecurringPattern:
    """Get a single bill by ID. Raises NoResultFound if not found."""
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == bill_id,
            RecurringPattern.user_id == user_id,
        )
    )
    return result.scalar_one()


async def create_manual_bill(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    label: str,
    estimated_amount: Decimal,
    frequency: str,
    next_expected_date: datetime,
    is_essential: bool = False,
    category_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> RecurringPattern:
    """Create a manual bill that feeds into forecast and safe-to-spend.

    Manual bills have:
    - is_manual=True
    - confidence=high (user explicitly stated it)
    - No merchant_id (user-entered)
    """
    # Validate frequency
    try:
        freq = Frequency(frequency)
    except ValueError:
        valid = [f.value for f in Frequency]
        raise ValueError(f"Invalid frequency '{frequency}'. Must be one of: {valid}")

    if estimated_amount <= 0:
        raise ValueError("estimated_amount must be positive")

    bill = RecurringPattern(
        user_id=user_id,
        merchant_id=None,  # Manual bills have no merchant
        category_id=category_id,
        estimated_amount=estimated_amount,
        amount_variance=Decimal("0.00"),
        frequency=freq,
        confidence=Confidence.high,  # User-stated = high confidence
        next_expected_date=next_expected_date,
        last_observed_date=None,
        is_active=True,
        is_manual=True,
        is_essential=is_essential,
        label=label,
    )
    db.add(bill)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="bill.created",
        entity_type="RecurringPattern",
        entity_id=bill.id,
        action="create_manual_bill",
        detail={
            "label": label,
            "amount": str(estimated_amount),
            "frequency": frequency,
            "is_essential": is_essential,
            "is_manual": True,
        },
        ip_address=ip_address,
    )

    return bill


async def toggle_essential(
    db: AsyncSession,
    *,
    bill_id: uuid.UUID,
    user_id: uuid.UUID,
    is_essential: bool,
    ip_address: str | None = None,
) -> RecurringPattern:
    """Toggle the essential flag on a bill.

    Essential bills are suppressed from cancellation recommendations.
    """
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == bill_id,
            RecurringPattern.user_id == user_id,
        )
    )
    bill = result.scalar_one()

    old_value = bill.is_essential
    bill.is_essential = is_essential
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="bill.essential_toggled",
        entity_type="RecurringPattern",
        entity_id=bill.id,
        action="toggle_essential",
        detail={
            "old_value": old_value,
            "new_value": is_essential,
            "label": bill.label,
        },
        ip_address=ip_address,
    )

    return bill


async def update_bill(
    db: AsyncSession,
    *,
    bill_id: uuid.UUID,
    user_id: uuid.UUID,
    label: str | None = None,
    estimated_amount: Decimal | None = None,
    frequency: str | None = None,
    next_expected_date: datetime | None = None,
    is_essential: bool | None = None,
    ip_address: str | None = None,
) -> RecurringPattern:
    """Update a manual bill's fields. Only manual bills can be fully edited."""
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == bill_id,
            RecurringPattern.user_id == user_id,
        )
    )
    bill = result.scalar_one()

    changes = {}

    if label is not None:
        changes["label"] = {"old": bill.label, "new": label}
        bill.label = label

    if estimated_amount is not None:
        if estimated_amount <= 0:
            raise ValueError("estimated_amount must be positive")
        changes["estimated_amount"] = {"old": str(bill.estimated_amount), "new": str(estimated_amount)}
        bill.estimated_amount = estimated_amount

    if frequency is not None:
        try:
            freq = Frequency(frequency)
        except ValueError:
            valid = [f.value for f in Frequency]
            raise ValueError(f"Invalid frequency '{frequency}'. Must be one of: {valid}")
        changes["frequency"] = {"old": bill.frequency.value, "new": frequency}
        bill.frequency = freq

    if next_expected_date is not None:
        changes["next_expected_date"] = {"new": str(next_expected_date)}
        bill.next_expected_date = next_expected_date

    if is_essential is not None:
        changes["is_essential"] = {"old": bill.is_essential, "new": is_essential}
        bill.is_essential = is_essential

    await db.flush()

    if changes:
        await audit_service.log_event(
            db,
            user_id=user_id,
            event_type="bill.updated",
            entity_type="RecurringPattern",
            entity_id=bill.id,
            action="update_bill",
            detail={"changes": changes},
            ip_address=ip_address,
        )

    return bill


async def deactivate_bill(
    db: AsyncSession,
    *,
    bill_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> RecurringPattern:
    """Deactivate a bill (soft-delete). Removes from forecast calculations."""
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == bill_id,
            RecurringPattern.user_id == user_id,
        )
    )
    bill = result.scalar_one()

    bill.is_active = False
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="bill.deactivated",
        entity_type="RecurringPattern",
        entity_id=bill.id,
        action="deactivate_bill",
        detail={"label": bill.label, "is_manual": bill.is_manual},
        ip_address=ip_address,
    )

    return bill


async def get_bill_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Get a summary of the user's bills.

    Returns total monthly cost, counts by confidence, essential count.
    """
    bills = await get_bills(db, user_id)

    total_monthly = Decimal("0.00")
    by_confidence = {"high": 0, "medium": 0, "low": 0}
    essential_count = 0
    manual_count = 0

    for bill in bills:
        # Normalize to monthly estimate
        monthly = _to_monthly(bill.estimated_amount, bill.frequency)
        total_monthly += monthly
        by_confidence[bill.confidence.value] += 1
        if bill.is_essential:
            essential_count += 1
        if bill.is_manual:
            manual_count += 1

    return {
        "total_bills": len(bills),
        "total_monthly_estimate": total_monthly,
        "by_confidence": by_confidence,
        "essential_count": essential_count,
        "manual_count": manual_count,
    }


def _to_monthly(amount: Decimal, frequency: Frequency) -> Decimal:
    """Convert an amount to its monthly equivalent."""
    multipliers = {
        Frequency.weekly: Decimal("4.33"),
        Frequency.biweekly: Decimal("2.17"),
        Frequency.monthly: Decimal("1"),
        Frequency.quarterly: Decimal("0.33"),
        Frequency.annual: Decimal("0.083"),
    }
    return round(amount * multipliers.get(frequency, Decimal("1")), 2)
