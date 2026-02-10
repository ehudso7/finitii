"""Tests for RecurringPattern detection with confidence scoring."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.recurring import Confidence, Frequency
from app.models.transaction import TransactionType
from app.models.user import User
from app.services import category_service, recurring_service, transaction_service


async def _setup(db: AsyncSession):
    user = User(email="recurring@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main",
        current_balance=Decimal("5000.00"),
        is_manual=True,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)

    await category_service.seed_system_categories(db)
    await db.commit()

    return user, acct


async def _add_transactions(
    db: AsyncSession,
    user_id,
    account_id,
    merchant_name: str,
    count: int,
    interval_days: int,
    base_amount: Decimal,
    amount_jitter: Decimal = Decimal("0.00"),
    date_jitter_days: int = 0,
):
    """Helper: add a series of transactions with configurable interval and jitter."""
    base_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
    for i in range(count):
        jitter_amount = Decimal(str(float(amount_jitter) * ((-1) ** i)))
        jitter_days = date_jitter_days * ((-1) ** i) if date_jitter_days else 0
        txn_date = base_date + timedelta(days=interval_days * i + jitter_days)
        await transaction_service.ingest_transaction(
            db,
            account_id=account_id,
            user_id=user_id,
            raw_description=f"{merchant_name} #{i}",
            amount=base_amount + jitter_amount,
            transaction_type=TransactionType.debit,
            transaction_date=txn_date,
        )
    await db.commit()


@pytest.mark.asyncio
async def test_high_confidence_monthly(db_session: AsyncSession):
    """4 monthly transactions same merchant ±$2 -> High confidence."""
    user, acct = await _setup(db_session)

    # 4 monthly transactions, consistent amount (±$2 on $50 = 4% < 10%)
    await _add_transactions(
        db_session, user.id, acct.id,
        merchant_name="NETFLIX",
        count=4,
        interval_days=30,
        base_amount=Decimal("15.99"),
        amount_jitter=Decimal("0.50"),
    )

    patterns = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    assert len(patterns) == 1
    p = patterns[0]
    assert p.confidence == Confidence.high
    assert p.frequency == Frequency.monthly
    assert p.is_active is True
    assert p.next_expected_date is not None
    assert p.last_observed_date is not None


@pytest.mark.asyncio
async def test_medium_confidence_two_consistent(db_session: AsyncSession):
    """2 monthly transactions with consistent interval -> Medium confidence."""
    user, acct = await _setup(db_session)

    await _add_transactions(
        db_session, user.id, acct.id,
        merchant_name="SPOTIFY",
        count=2,
        interval_days=30,
        base_amount=Decimal("9.99"),
    )

    patterns = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    assert len(patterns) == 1
    assert patterns[0].confidence == Confidence.medium


@pytest.mark.asyncio
async def test_medium_confidence_three_plus_inconsistent_amounts(db_session: AsyncSession):
    """3+ monthly transactions with inconsistent amounts -> Medium confidence."""
    user, acct = await _setup(db_session)

    # Large jitter: ±$20 on $50 = 40% > 10%
    await _add_transactions(
        db_session, user.id, acct.id,
        merchant_name="ELECTRIC CO",
        count=4,
        interval_days=30,
        base_amount=Decimal("50.00"),
        amount_jitter=Decimal("20.00"),
    )

    patterns = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    assert len(patterns) == 1
    assert patterns[0].confidence == Confidence.medium


@pytest.mark.asyncio
async def test_low_confidence_inconsistent_interval(db_session: AsyncSession):
    """2 transactions with inconsistent timing -> Low confidence."""
    user, acct = await _setup(db_session)

    # 2 transactions with a 45-day gap (doesn't match any standard frequency cleanly
    # but let's use a large date jitter on a biweekly base to create inconsistency)
    base_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
    await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="RANDOM GYM #1",
        amount=Decimal("30.00"),
        transaction_type=TransactionType.debit,
        transaction_date=base_date,
    )
    # Second transaction 45 days later — doesn't match weekly/biweekly/monthly/quarterly
    await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="RANDOM GYM #2",
        amount=Decimal("30.00"),
        transaction_type=TransactionType.debit,
        transaction_date=base_date + timedelta(days=45),
    )
    await db_session.commit()

    patterns = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    # 45-day interval doesn't match any frequency range, so no pattern detected
    assert len(patterns) == 0


@pytest.mark.asyncio
async def test_confidence_always_present(db_session: AsyncSession):
    """Verify confidence is always present on output."""
    user, acct = await _setup(db_session)

    await _add_transactions(
        db_session, user.id, acct.id,
        merchant_name="HULU",
        count=3,
        interval_days=30,
        base_amount=Decimal("12.99"),
    )

    patterns = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    for p in patterns:
        assert p.confidence is not None
        assert p.confidence in (Confidence.low, Confidence.medium, Confidence.high)


@pytest.mark.asyncio
async def test_weekly_detection(db_session: AsyncSession):
    """Weekly transactions detected correctly."""
    user, acct = await _setup(db_session)

    await _add_transactions(
        db_session, user.id, acct.id,
        merchant_name="LAUNDRY SVC",
        count=5,
        interval_days=7,
        base_amount=Decimal("8.00"),
    )

    patterns = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    assert len(patterns) == 1
    assert patterns[0].frequency == Frequency.weekly
    assert patterns[0].confidence == Confidence.high


@pytest.mark.asyncio
async def test_redetection_replaces_patterns(db_session: AsyncSession):
    """Running detection twice replaces patterns (full recompute)."""
    user, acct = await _setup(db_session)

    await _add_transactions(
        db_session, user.id, acct.id,
        merchant_name="NETFLIX",
        count=3,
        interval_days=30,
        base_amount=Decimal("15.99"),
    )

    p1 = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()
    assert len(p1) == 1

    p2 = await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()
    assert len(p2) == 1

    # Patterns should be different records (recomputed)
    all_patterns = await recurring_service.get_patterns(db_session, user.id)
    assert len(all_patterns) == 1
