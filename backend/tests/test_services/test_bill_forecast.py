"""Test that manual bills feed into forecast and safe-to-spend."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.user import User
from app.services import bill_service, forecast_service


async def _create_user(db: AsyncSession) -> User:
    user = User(email="billfcast@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_checking(db: AsyncSession, user: User, balance: Decimal) -> Account:
    acct = Account(
        user_id=user.id, account_type=AccountType.checking,
        institution_name="Bank", account_name="Checking",
        current_balance=balance, available_balance=balance,
    )
    db.add(acct)
    await db.flush()
    return acct


@pytest.mark.asyncio
async def test_manual_bill_feeds_safe_to_spend_week(db_session: AsyncSession):
    """Manual bill due this week reduces safe-to-spend-week."""
    user = await _create_user(db_session)
    await _create_checking(db_session, user, Decimal("1000.00"))

    # No bills: STS week = 1000
    snapshot1 = await forecast_service.compute_forecast(db_session, user.id)
    assert snapshot1.safe_to_spend_week == Decimal("1000.00")

    # Add manual bill due in 3 days
    today = forecast_service._today_utc()
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Internet",
        estimated_amount=Decimal("75.00"), frequency="monthly",
        next_expected_date=today + timedelta(days=3),
    )

    # STS week should now be reduced
    snapshot2 = await forecast_service.compute_forecast(db_session, user.id)
    assert snapshot2.safe_to_spend_week == Decimal("925.00")


@pytest.mark.asyncio
async def test_manual_bill_feeds_safe_to_spend_today(db_session: AsyncSession):
    """Manual bill due today reduces safe-to-spend-today."""
    user = await _create_user(db_session)
    await _create_checking(db_session, user, Decimal("500.00"))

    today = forecast_service._today_utc()
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Gym",
        estimated_amount=Decimal("50.00"), frequency="monthly",
        next_expected_date=today + timedelta(hours=12),  # Due today
    )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)
    assert snapshot.safe_to_spend_today == Decimal("450.00")


@pytest.mark.asyncio
async def test_manual_bill_feeds_30_day_projection(db_session: AsyncSession):
    """Manual bills appear in 30-day projection."""
    user = await _create_user(db_session)
    await _create_checking(db_session, user, Decimal("2000.00"))

    today = forecast_service._today_utc()
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Rent",
        estimated_amount=Decimal("1500.00"), frequency="monthly",
        next_expected_date=today + timedelta(days=15),
    )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    # With $2000 and $1500 rent due in 15 days, end balance should be lower
    assert snapshot.projected_end_balance < Decimal("2000.00")


@pytest.mark.asyncio
async def test_deactivated_bill_not_in_forecast(db_session: AsyncSession):
    """Deactivated bills should NOT appear in forecast."""
    user = await _create_user(db_session)
    await _create_checking(db_session, user, Decimal("1000.00"))

    today = forecast_service._today_utc()
    bill = await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Cancelled Sub",
        estimated_amount=Decimal("100.00"), frequency="monthly",
        next_expected_date=today + timedelta(days=2),
    )

    # Deactivate
    await bill_service.deactivate_bill(
        db_session, bill_id=bill.id, user_id=user.id,
    )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)
    # Should not be reduced by the deactivated bill
    assert snapshot.safe_to_spend_week == Decimal("1000.00")


@pytest.mark.asyncio
async def test_manual_bill_assumptions_included(db_session: AsyncSession):
    """Forecast assumptions should mention recurring patterns including manual bills."""
    user = await _create_user(db_session)
    await _create_checking(db_session, user, Decimal("3000.00"))

    today = forecast_service._today_utc()
    await bill_service.create_manual_bill(
        db_session, user_id=user.id, label="Rent",
        estimated_amount=Decimal("1500.00"), frequency="monthly",
        next_expected_date=today + timedelta(days=10),
    )

    snapshot = await forecast_service.compute_forecast(db_session, user.id)

    # Assumptions should mention the recurring pattern
    assert any("recurring" in a.lower() for a in snapshot.assumptions)
