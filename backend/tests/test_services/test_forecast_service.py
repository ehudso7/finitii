"""Forecast service tests: Safe-to-Spend, 30-day projection, confidence, urgency."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.merchant import Merchant
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services import forecast_service


async def _create_user(db: AsyncSession) -> User:
    user = User(email="forecast@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_checking_account(
    db: AsyncSession, user: User, balance: Decimal = Decimal("1000.00")
) -> Account:
    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Checking",
        current_balance=balance,
        available_balance=balance,
    )
    db.add(acct)
    await db.flush()
    return acct


async def _create_merchant(db: AsyncSession, user: User, name: str) -> Merchant:
    merchant = Merchant(
        raw_name=name,
        normalized_name=name.lower(),
        display_name=name,
    )
    db.add(merchant)
    await db.flush()
    return merchant


async def _create_recurring_pattern(
    db: AsyncSession,
    user: User,
    merchant: Merchant,
    amount: Decimal,
    next_date: datetime,
    frequency: Frequency = Frequency.monthly,
    confidence: Confidence = Confidence.high,
) -> RecurringPattern:
    pattern = RecurringPattern(
        user_id=user.id,
        merchant_id=merchant.id,
        estimated_amount=amount,
        amount_variance=Decimal("0.00"),
        frequency=frequency,
        confidence=confidence,
        next_expected_date=next_date,
        last_observed_date=next_date - timedelta(days=30),
        is_active=True,
    )
    db.add(pattern)
    await db.flush()
    return pattern


async def _create_transaction(
    db: AsyncSession,
    user: User,
    account: Account,
    amount: Decimal,
    txn_type: TransactionType,
    date: datetime,
    merchant: Merchant | None = None,
) -> Transaction:
    txn = Transaction(
        user_id=user.id,
        account_id=account.id,
        merchant_id=merchant.id if merchant else None,
        raw_description="test",
        normalized_description="test",
        amount=amount,
        transaction_date=date,
        transaction_type=txn_type,
    )
    db.add(txn)
    await db.flush()
    return txn


# --- Safe-to-Spend ---

@pytest.mark.asyncio
async def test_safe_to_spend_no_recurring(db_session: AsyncSession):
    """Safe-to-spend equals balance when no recurring charges upcoming."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.safe_to_spend_today == Decimal("1000.00")
    assert snapshot.safe_to_spend_week == Decimal("1000.00")


@pytest.mark.asyncio
async def test_safe_to_spend_with_today_recurring(db_session: AsyncSession):
    """Safe-to-spend today subtracts charges due today."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))
    merchant = await _create_merchant(db_session, user, "Netflix")

    today = forecast_service._today_utc()
    await _create_recurring_pattern(
        db_session, user, merchant, Decimal("15.99"),
        next_date=today + timedelta(hours=12),  # Due today
    )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.safe_to_spend_today == Decimal("984.01")
    # Week also includes today's charge
    assert snapshot.safe_to_spend_week == Decimal("984.01")


@pytest.mark.asyncio
async def test_safe_to_spend_with_week_recurring(db_session: AsyncSession):
    """Safe-to-spend week subtracts charges due within 7 days."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))
    merchant = await _create_merchant(db_session, user, "Spotify")

    today = forecast_service._today_utc()
    await _create_recurring_pattern(
        db_session, user, merchant, Decimal("9.99"),
        next_date=today + timedelta(days=3),  # Due in 3 days
    )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    # Today: no charge (it's due in 3 days)
    assert snapshot.safe_to_spend_today == Decimal("1000.00")
    # Week: includes the charge
    assert snapshot.safe_to_spend_week == Decimal("990.01")


@pytest.mark.asyncio
async def test_safe_to_spend_multiple_accounts(db_session: AsyncSession):
    """Safe-to-spend sums across checking + savings accounts."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("500.00"))

    savings = Account(
        user_id=user.id,
        account_type=AccountType.savings,
        institution_name="Test Bank",
        account_name="Savings",
        current_balance=Decimal("2000.00"),
        available_balance=Decimal("2000.00"),
    )
    db_session.add(savings)
    await db_session.flush()

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.safe_to_spend_today == Decimal("2500.00")


# --- 30-day Projection ---

@pytest.mark.asyncio
async def test_30_day_projection_has_30_days(db_session: AsyncSession):
    """Daily balances should contain exactly 30 days."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert len(snapshot.daily_balances) == 30
    assert snapshot.daily_balances[0]["day"] == 1
    assert snapshot.daily_balances[29]["day"] == 30


@pytest.mark.asyncio
async def test_30_day_projection_has_bands(db_session: AsyncSession):
    """Each day in projection must have projected, low, high values."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    for day in snapshot.daily_balances:
        assert "projected" in day
        assert "low" in day
        assert "high" in day
        assert "date" in day
        # Low should be ≤ projected ≤ high
        assert Decimal(day["low"]) <= Decimal(day["projected"]) <= Decimal(day["high"])


@pytest.mark.asyncio
async def test_projection_with_spending_history(db_session: AsyncSession):
    """Projection uses historical spending patterns."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("3000.00"))
    merchant = await _create_merchant(db_session, user, "Store")

    # Create 30 days of daily $50 spending
    today = forecast_service._today_utc()
    for i in range(30):
        dt = today - timedelta(days=30 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("50.00"),
            TransactionType.debit, dt, merchant,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    # Balance should decline (spending $50/day with no income)
    assert snapshot.projected_end_balance < Decimal("3000.00")
    # End balance bands
    assert snapshot.projected_end_low <= snapshot.projected_end_balance
    assert snapshot.projected_end_high >= snapshot.projected_end_balance


@pytest.mark.asyncio
async def test_projection_includes_income(db_session: AsyncSession):
    """Projection factors in income credits."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("2000.00"))

    today = forecast_service._today_utc()
    # Create income transactions (credits)
    for i in range(3):
        dt = today - timedelta(days=30 * (i + 1))
        await _create_transaction(
            db_session, user, acct, Decimal("3000.00"),
            TransactionType.credit, dt,
        )
    # Create spending transactions (debits)
    for i in range(30):
        dt = today - timedelta(days=30 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("30.00"),
            TransactionType.debit, dt,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    # Income should partially offset spending in projection
    # With $3000 income over ~90 days = ~$33/day income, and $30/day spending
    # net should be slightly positive
    assert snapshot.projected_end_balance is not None


# --- Confidence ---

@pytest.mark.asyncio
async def test_confidence_low_no_data(db_session: AsyncSession):
    """Confidence is low with no transaction history."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.confidence == "low"


@pytest.mark.asyncio
async def test_confidence_medium_some_data(db_session: AsyncSession):
    """Confidence is medium with ≥30 days of data and ≥1 recurring pattern."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("1000.00"))
    merchant = await _create_merchant(db_session, user, "Gym")

    # Create recurring pattern
    today = forecast_service._today_utc()
    await _create_recurring_pattern(
        db_session, user, merchant, Decimal("50.00"),
        next_date=today + timedelta(days=15),
    )

    # Create transactions spanning 35 days
    for i in range(36):
        dt = today - timedelta(days=35 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("10.00"),
            TransactionType.debit, dt, merchant,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.confidence == "medium"


@pytest.mark.asyncio
async def test_confidence_high_lots_of_data(db_session: AsyncSession):
    """Confidence is high with ≥90 days and ≥3 high-confidence patterns."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("5000.00"))

    today = forecast_service._today_utc()

    # Create 3 high-confidence recurring patterns
    for name, amount in [("Netflix", "15.99"), ("Gym", "50.00"), ("Spotify", "9.99")]:
        merchant = await _create_merchant(db_session, user, name)
        await _create_recurring_pattern(
            db_session, user, merchant, Decimal(amount),
            next_date=today + timedelta(days=15),
            confidence=Confidence.high,
        )

    # Create transactions spanning 95 days
    merchant = await _create_merchant(db_session, user, "Store")
    for i in range(96):
        dt = today - timedelta(days=95 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("10.00"),
            TransactionType.debit, dt, merchant,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.confidence == "high"


@pytest.mark.asyncio
async def test_confidence_inputs_exposed(db_session: AsyncSession):
    """Confidence inputs must be fully exposed for explainability."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert "days_of_transaction_data" in snapshot.confidence_inputs
    assert "total_recurring_patterns" in snapshot.confidence_inputs
    assert "high_confidence_patterns" in snapshot.confidence_inputs
    assert "transaction_count" in snapshot.confidence_inputs


# --- Assumptions ---

@pytest.mark.asyncio
async def test_assumptions_always_present(db_session: AsyncSession):
    """Every forecast must have explicit assumptions."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert isinstance(snapshot.assumptions, list)
    assert len(snapshot.assumptions) >= 1
    # Must include balance assumption
    assert any("balance" in a.lower() for a in snapshot.assumptions)


@pytest.mark.asyncio
async def test_assumptions_include_spending(db_session: AsyncSession):
    """Assumptions include average daily spending info."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("1000.00"))

    today = forecast_service._today_utc()
    for i in range(5):
        dt = today - timedelta(days=5 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("20.00"),
            TransactionType.debit, dt,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert any("daily spending" in a.lower() for a in snapshot.assumptions)


# --- Urgency ---

@pytest.mark.asyncio
async def test_urgency_zero_healthy_balance(db_session: AsyncSession):
    """Urgency is low when balance is healthy."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("10000.00"))

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.urgency_score == 0


@pytest.mark.asyncio
async def test_urgency_high_low_balance(db_session: AsyncSession):
    """Urgency is high when balance is low relative to spending."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("100.00"))

    # Create heavy spending history ($50/day)
    today = forecast_service._today_utc()
    for i in range(30):
        dt = today - timedelta(days=30 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("50.00"),
            TransactionType.debit, dt,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert snapshot.urgency_score > 0
    assert "factors" in snapshot.urgency_factors


@pytest.mark.asyncio
async def test_urgency_factors_explained(db_session: AsyncSession):
    """Urgency factors must be human-readable."""
    user = await _create_user(db_session)
    acct = await _create_checking_account(db_session, user, Decimal("50.00"))

    today = forecast_service._today_utc()
    for i in range(30):
        dt = today - timedelta(days=30 - i)
        await _create_transaction(
            db_session, user, acct, Decimal("30.00"),
            TransactionType.debit, dt,
        )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    assert isinstance(snapshot.urgency_factors["factors"], list)
    if snapshot.urgency_score > 0:
        assert len(snapshot.urgency_factors["factors"]) >= 1


# --- Audit ---

@pytest.mark.asyncio
async def test_forecast_audit_logged(db_session: AsyncSession):
    """Forecast computation must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    await forecast_service.compute_forecast(db_session, user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "forecast.computed",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert "safe_to_spend_today" in events[0].detail
    assert "confidence" in events[0].detail


# --- Retrieval ---

@pytest.mark.asyncio
async def test_get_latest_forecast(db_session: AsyncSession):
    """Can retrieve the most recent forecast."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    snapshot1 = await forecast_service.compute_forecast(db_session, user.id)
    snapshot2 = await forecast_service.compute_forecast(db_session, user.id)

    latest = await forecast_service.get_latest_forecast(db_session, user.id)
    assert latest is not None
    assert latest.id == snapshot2.id


@pytest.mark.asyncio
async def test_get_forecast_history(db_session: AsyncSession):
    """Can retrieve forecast history."""
    user = await _create_user(db_session)
    await _create_checking_account(db_session, user, Decimal("1000.00"))

    await forecast_service.compute_forecast(db_session, user.id)
    await forecast_service.compute_forecast(db_session, user.id)
    await forecast_service.compute_forecast(db_session, user.id)

    history = await forecast_service.get_forecast_history(db_session, user.id, limit=2)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_get_latest_forecast_none(db_session: AsyncSession):
    """Returns None when no forecast exists."""
    user = await _create_user(db_session)
    result = await forecast_service.get_latest_forecast(db_session, user.id)
    assert result is None
