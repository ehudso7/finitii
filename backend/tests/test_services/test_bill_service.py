"""Bill service tests: derived views, manual bills, essential toggle, summary."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.user import User
from app.services import bill_service


async def _create_user(db: AsyncSession) -> User:
    user = User(email="bill@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_detected_pattern(
    db: AsyncSession, user: User, amount: Decimal = Decimal("15.99"),
    label: str | None = None, is_essential: bool = False,
) -> RecurringPattern:
    """Create a detected (non-manual) recurring pattern."""
    merchant = Merchant(
        raw_name="TestMerchant", normalized_name="testmerchant",
        display_name="TestMerchant",
    )
    db.add(merchant)
    await db.flush()

    pattern = RecurringPattern(
        user_id=user.id,
        merchant_id=merchant.id,
        estimated_amount=amount,
        amount_variance=Decimal("0.00"),
        frequency=Frequency.monthly,
        confidence=Confidence.high,
        next_expected_date=datetime.now(timezone.utc) + timedelta(days=15),
        last_observed_date=datetime.now(timezone.utc) - timedelta(days=15),
        is_active=True,
        is_manual=False,
        is_essential=is_essential,
        label=label,
    )
    db.add(pattern)
    await db.flush()
    return pattern


# --- List bills ---

@pytest.mark.asyncio
async def test_get_bills_empty(db_session: AsyncSession):
    """Returns empty list when user has no bills."""
    user = await _create_user(db_session)
    bills = await bill_service.get_bills(db_session, user.id)
    assert bills == []


@pytest.mark.asyncio
async def test_get_bills_includes_detected(db_session: AsyncSession):
    """Detected recurring patterns appear as bills."""
    user = await _create_user(db_session)
    await _create_detected_pattern(db_session, user)
    bills = await bill_service.get_bills(db_session, user.id)
    assert len(bills) == 1
    assert bills[0].is_manual is False


@pytest.mark.asyncio
async def test_get_bills_includes_manual(db_session: AsyncSession):
    """Manual bills appear in the list."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Rent",
        estimated_amount=Decimal("1500.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=5),
    )
    bills = await bill_service.get_bills(db_session, user.id)
    assert len(bills) == 1
    assert bills[0].is_manual is True
    assert bills[0].label == "Rent"


@pytest.mark.asyncio
async def test_get_bills_confidence_always_visible(db_session: AsyncSession):
    """Confidence must be visible on every bill (PRD rule)."""
    user = await _create_user(db_session)
    await _create_detected_pattern(db_session, user)
    now = datetime.now(timezone.utc)
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Insurance",
        estimated_amount=Decimal("200.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=10),
    )
    bills = await bill_service.get_bills(db_session, user.id)
    for bill in bills:
        assert bill.confidence is not None
        assert bill.confidence.value in ("high", "medium", "low")


# --- Create manual bill ---

@pytest.mark.asyncio
async def test_create_manual_bill(db_session: AsyncSession):
    """Manual bill is created with high confidence."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    bill = await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Rent",
        estimated_amount=Decimal("1500.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=1),
    )

    assert bill.is_manual is True
    assert bill.confidence == Confidence.high
    assert bill.label == "Rent"
    assert bill.estimated_amount == Decimal("1500.00")
    assert bill.merchant_id is None
    assert bill.is_active is True


@pytest.mark.asyncio
async def test_create_manual_bill_essential(db_session: AsyncSession):
    """Manual bill can be marked essential at creation."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    bill = await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Mortgage",
        estimated_amount=Decimal("2000.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=1),
        is_essential=True,
    )

    assert bill.is_essential is True


@pytest.mark.asyncio
async def test_create_manual_bill_invalid_frequency(db_session: AsyncSession):
    """Invalid frequency raises ValueError."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="Invalid frequency"):
        await bill_service.create_manual_bill(
            db_session, user_id=user.id, label="Bad",
            estimated_amount=Decimal("10.00"), frequency="daily",
            next_expected_date=now,
        )


@pytest.mark.asyncio
async def test_create_manual_bill_zero_amount(db_session: AsyncSession):
    """Zero amount raises ValueError."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="positive"):
        await bill_service.create_manual_bill(
            db_session, user_id=user.id, label="Free",
            estimated_amount=Decimal("0.00"), frequency="monthly",
            next_expected_date=now,
        )


@pytest.mark.asyncio
async def test_create_manual_bill_audit_logged(db_session: AsyncSession):
    """Manual bill creation must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Gym",
        estimated_amount=Decimal("50.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=5),
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "bill.created",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].detail["label"] == "Gym"
    assert events[0].detail["is_manual"] is True


# --- Toggle essential ---

@pytest.mark.asyncio
async def test_toggle_essential_on(db_session: AsyncSession):
    """Can toggle a bill to essential."""
    user = await _create_user(db_session)
    pattern = await _create_detected_pattern(db_session, user)
    assert pattern.is_essential is False

    updated = await bill_service.toggle_essential(
        db_session, bill_id=pattern.id, user_id=user.id, is_essential=True,
    )
    assert updated.is_essential is True


@pytest.mark.asyncio
async def test_toggle_essential_off(db_session: AsyncSession):
    """Can toggle essential off."""
    user = await _create_user(db_session)
    pattern = await _create_detected_pattern(db_session, user, is_essential=True)

    updated = await bill_service.toggle_essential(
        db_session, bill_id=pattern.id, user_id=user.id, is_essential=False,
    )
    assert updated.is_essential is False


@pytest.mark.asyncio
async def test_toggle_essential_audit_logged(db_session: AsyncSession):
    """Essential toggle must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    pattern = await _create_detected_pattern(db_session, user)

    await bill_service.toggle_essential(
        db_session, bill_id=pattern.id, user_id=user.id, is_essential=True,
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "bill.essential_toggled",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1


# --- Update bill ---

@pytest.mark.asyncio
async def test_update_bill_label(db_session: AsyncSession):
    """Can update a bill's label."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    bill = await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Old Name",
        estimated_amount=Decimal("100.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=5),
    )

    updated = await bill_service.update_bill(
        db_session, bill_id=bill.id, user_id=user.id, label="New Name",
    )
    assert updated.label == "New Name"


@pytest.mark.asyncio
async def test_update_bill_amount(db_session: AsyncSession):
    """Can update a bill's amount."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    bill = await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Rent",
        estimated_amount=Decimal("1500.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=5),
    )

    updated = await bill_service.update_bill(
        db_session, bill_id=bill.id, user_id=user.id,
        estimated_amount=Decimal("1600.00"),
    )
    assert updated.estimated_amount == Decimal("1600.00")


# --- Deactivate ---

@pytest.mark.asyncio
async def test_deactivate_bill(db_session: AsyncSession):
    """Deactivating a bill sets is_active=False."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    bill = await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Cancel Me",
        estimated_amount=Decimal("10.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=5),
    )

    deactivated = await bill_service.deactivate_bill(
        db_session, bill_id=bill.id, user_id=user.id,
    )
    assert deactivated.is_active is False

    # Should not appear in active bills list
    bills = await bill_service.get_bills(db_session, user.id)
    assert len(bills) == 0


# --- Summary ---

@pytest.mark.asyncio
async def test_bill_summary(db_session: AsyncSession):
    """Summary includes total monthly cost and counts."""
    user = await _create_user(db_session)
    now = datetime.now(timezone.utc)

    await _create_detected_pattern(db_session, user, Decimal("15.99"))
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Rent",
        estimated_amount=Decimal("1500.00"), frequency="monthly",
        next_expected_date=now + timedelta(days=5),
        is_essential=True,
    )

    summary = await bill_service.get_bill_summary(db_session, user.id)

    assert summary["total_bills"] == 2
    assert summary["total_monthly_estimate"] > Decimal("1500.00")
    assert summary["essential_count"] == 1
    assert summary["manual_count"] == 1
    assert summary["by_confidence"]["high"] == 2


@pytest.mark.asyncio
async def test_bill_summary_empty(db_session: AsyncSession):
    """Summary returns zeros when no bills exist."""
    user = await _create_user(db_session)
    summary = await bill_service.get_bill_summary(db_session, user.id)

    assert summary["total_bills"] == 0
    assert summary["total_monthly_estimate"] == Decimal("0.00")
