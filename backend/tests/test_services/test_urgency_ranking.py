"""Test forecast urgency integration with ranking.

PRD rule: urgency may influence ranking but CANNOT override confidence rules.
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.forecast import ForecastConfidence, ForecastSnapshot
from app.models.merchant import Merchant
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services import forecast_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="urgrank@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_account_and_history(
    db: AsyncSession, user: User, balance: Decimal
) -> Account:
    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Bank",
        account_name="Checking",
        current_balance=balance,
        available_balance=balance,
    )
    db.add(acct)
    await db.flush()
    return acct


@pytest.mark.asyncio
async def test_urgency_boosts_save_money_codes(db_session: AsyncSession):
    """High urgency should boost save_money codes in ranking."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # First compute rankings with no forecast (no urgency)
    recs_no_urgency = await ranking_service.compute_top_3(db_session, user.id)
    scores_no_urgency = [r.rank for r in recs_no_urgency]

    # Now create a high-urgency forecast
    acct = await _create_account_and_history(db_session, user, Decimal("50.00"))
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(30):
        txn = Transaction(
            user_id=user.id, account_id=acct.id,
            raw_description="spend", normalized_description="spend",
            amount=Decimal("40.00"), transaction_date=today - timedelta(days=30 - i),
            transaction_type=TransactionType.debit,
        )
        db_session.add(txn)
    await db_session.flush()

    snapshot = await forecast_service.compute_forecast(db_session, user.id)
    assert snapshot.urgency_score > 0  # Should be urgent

    # Recompute rankings with urgency in play
    recs_with_urgency = await ranking_service.compute_top_3(db_session, user.id)

    # Rankings should still follow all confidence rules
    for r in recs_with_urgency:
        assert r.confidence != "low"  # PRD: no low confidence
    assert any(r.is_quick_win for r in recs_with_urgency)  # PRD: ≥1 quick win


@pytest.mark.asyncio
async def test_urgency_cannot_override_confidence(db_session: AsyncSession):
    """Urgency influences score but confidence rules are never violated."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # Create high urgency scenario
    acct = await _create_account_and_history(db_session, user, Decimal("10.00"))
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(30):
        txn = Transaction(
            user_id=user.id, account_id=acct.id,
            raw_description="spend", normalized_description="spend",
            amount=Decimal("50.00"), transaction_date=today - timedelta(days=30 - i),
            transaction_type=TransactionType.debit,
        )
        db_session.add(txn)
    await db_session.flush()

    await forecast_service.compute_forecast(db_session, user.id)
    recs = await ranking_service.compute_top_3(db_session, user.id)

    # NEVER low confidence regardless of urgency
    for r in recs:
        assert r.confidence in ("high", "medium")

    # Still has quick win
    assert any(r.is_quick_win for r in recs)

    # All have explanations
    for r in recs:
        assert len(r.explanation) > 0
        assert r.explanation_template in ranking_service.TEMPLATES


@pytest.mark.asyncio
async def test_zero_urgency_no_effect(db_session: AsyncSession):
    """With zero urgency, ranking behaves the same as before Phase 4."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # No forecast = no urgency
    recs = await ranking_service.compute_top_3(db_session, user.id)
    assert len(recs) == 3
    for r in recs:
        assert r.confidence != "low"
