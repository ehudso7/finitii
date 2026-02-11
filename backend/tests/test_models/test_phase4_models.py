"""Phase 4 model tests: ForecastSnapshot, ForecastConfidence."""

import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.user import User


async def _create_user(db: AsyncSession) -> User:
    user = User(email="p4model@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_forecast_snapshot_create(db_session: AsyncSession):
    """ForecastSnapshot can be created with all fields."""
    user = await _create_user(db_session)

    snapshot = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("450.00"),
        safe_to_spend_week=Decimal("300.00"),
        daily_balances=[
            {"day": 1, "date": "2026-02-11", "projected": "950.00",
             "low": "900.00", "high": "1000.00"},
        ],
        projected_end_balance=Decimal("500.00"),
        projected_end_low=Decimal("200.00"),
        projected_end_high=Decimal("800.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={"days_of_transaction_data": 45, "total_recurring_patterns": 2},
        assumptions=["Current balance: $1000.00", "Average daily spend: $15.00"],
        urgency_score=25,
        urgency_factors={"score": 25, "factors": ["Balance covers ~20 days"]},
    )
    db_session.add(snapshot)
    await db_session.flush()

    result = await db_session.execute(
        select(ForecastSnapshot).where(ForecastSnapshot.id == snapshot.id)
    )
    fetched = result.scalar_one()
    assert fetched.safe_to_spend_today == Decimal("450.00")
    assert fetched.safe_to_spend_week == Decimal("300.00")
    assert fetched.projected_end_balance == Decimal("500.00")
    assert fetched.confidence == ForecastConfidence.medium
    assert len(fetched.daily_balances) == 1
    assert len(fetched.assumptions) == 2
    assert fetched.urgency_score == 25


@pytest.mark.asyncio
async def test_forecast_confidence_enum(db_session: AsyncSession):
    """ForecastConfidence enum has correct values."""
    assert ForecastConfidence.high.value == "high"
    assert ForecastConfidence.medium.value == "medium"
    assert ForecastConfidence.low.value == "low"


@pytest.mark.asyncio
async def test_forecast_snapshot_negative_safe_to_spend(db_session: AsyncSession):
    """Safe-to-spend can be negative (valid state)."""
    user = await _create_user(db_session)

    snapshot = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("-50.00"),
        safe_to_spend_week=Decimal("-200.00"),
        daily_balances=[],
        projected_end_balance=Decimal("-100.00"),
        projected_end_low=Decimal("-300.00"),
        projected_end_high=Decimal("50.00"),
        confidence=ForecastConfidence.low,
        confidence_inputs={"days_of_transaction_data": 5},
        assumptions=["Insufficient data"],
        urgency_score=85,
        urgency_factors={"score": 85, "factors": ["Negative safe-to-spend"]},
    )
    db_session.add(snapshot)
    await db_session.flush()

    result = await db_session.execute(
        select(ForecastSnapshot).where(ForecastSnapshot.id == snapshot.id)
    )
    fetched = result.scalar_one()
    assert fetched.safe_to_spend_today == Decimal("-50.00")
    assert fetched.urgency_score == 85


@pytest.mark.asyncio
async def test_forecast_snapshot_has_timestamps(db_session: AsyncSession):
    """ForecastSnapshot has created_at and computed_at timestamps."""
    user = await _create_user(db_session)

    snapshot = ForecastSnapshot(
        user_id=user.id,
        safe_to_spend_today=Decimal("100.00"),
        safe_to_spend_week=Decimal("50.00"),
        daily_balances=[],
        projected_end_balance=Decimal("100.00"),
        projected_end_low=Decimal("50.00"),
        projected_end_high=Decimal("150.00"),
        confidence=ForecastConfidence.medium,
        confidence_inputs={},
        assumptions=[],
        urgency_score=0,
        urgency_factors={"score": 0, "factors": []},
    )
    db_session.add(snapshot)
    await db_session.flush()

    assert snapshot.created_at is not None
    assert snapshot.computed_at is not None
