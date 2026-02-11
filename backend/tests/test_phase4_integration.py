"""Phase 4 end-to-end integration test.

Full flow: create account → add transactions → compute forecast →
verify Safe-to-Spend + 30-day projection + confidence + assumptions +
urgency → compute Top 3 (urgency-influenced) → verify confidence rules hold.
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.merchant import Merchant
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.transaction import Transaction, TransactionType


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p4e2e@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p4e2e@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


async def _setup_financial_data(db: AsyncSession, user_id_str: str):
    """Set up realistic financial data for integration test."""
    uid = uuid.UUID(user_id_str)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Create checking account with $2500
    acct = Account(
        user_id=uid,
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Main Checking",
        current_balance=Decimal("2500.00"),
        available_balance=Decimal("2500.00"),
    )
    db.add(acct)
    await db.flush()

    # Create merchants
    netflix = Merchant(raw_name="Netflix", normalized_name="netflix", display_name="Netflix")
    grocery = Merchant(raw_name="Grocery Store", normalized_name="grocery store", display_name="Grocery Store")
    employer = Merchant(raw_name="Employer Inc", normalized_name="employer inc", display_name="Employer Inc")
    db.add_all([netflix, grocery, employer])
    await db.flush()

    # Create recurring patterns
    # Netflix monthly $15.99 due in 5 days
    netflix_pattern = RecurringPattern(
        user_id=uid, merchant_id=netflix.id,
        estimated_amount=Decimal("15.99"), amount_variance=Decimal("0.00"),
        frequency=Frequency.monthly, confidence=Confidence.high,
        next_expected_date=today + timedelta(days=5),
        last_observed_date=today - timedelta(days=25),
        is_active=True,
    )
    db.add(netflix_pattern)

    # Create 60 days of transaction history
    for i in range(60):
        dt = today - timedelta(days=60 - i)

        # Daily grocery spend ~$25 (debit)
        txn = Transaction(
            user_id=uid, account_id=acct.id, merchant_id=grocery.id,
            raw_description="GROCERY STORE", normalized_description="Grocery Store",
            amount=Decimal("25.00"), transaction_date=dt,
            transaction_type=TransactionType.debit,
        )
        db.add(txn)

        # Bi-weekly paycheck ($2000 credit, every 14 days)
        if i % 14 == 0:
            pay = Transaction(
                user_id=uid, account_id=acct.id, merchant_id=employer.id,
                raw_description="EMPLOYER INC PAYROLL",
                normalized_description="Employer Inc",
                amount=Decimal("2000.00"), transaction_date=dt,
                transaction_type=TransactionType.credit,
            )
            db.add(pay)

    await db.flush()


@pytest.mark.asyncio
async def test_phase4_full_forecast_flow(client: AsyncClient, db_session: AsyncSession):
    """End-to-end: forecast with Safe-to-Spend, projection, confidence, urgency."""
    headers, user_id = await _register_and_login(client)
    await _setup_financial_data(db_session, user_id)

    # 1. Compute forecast
    resp = await client.post("/forecast/compute", headers=headers)
    assert resp.status_code == 201
    forecast = resp.json()

    # 2. Verify Safe-to-Spend
    sts_today = Decimal(forecast["safe_to_spend_today"])
    sts_week = Decimal(forecast["safe_to_spend_week"])
    assert sts_today > 0  # Should be positive with $2500 balance
    # Week should be ≤ today (more charges upcoming)
    assert sts_week <= sts_today

    # 3. Verify 30-day projection
    daily = forecast["daily_balances"]
    assert len(daily) == 30
    for day in daily:
        assert "day" in day
        assert "date" in day
        assert "projected" in day
        assert "low" in day
        assert "high" in day
        # Volatility bands: low ≤ projected ≤ high
        assert Decimal(day["low"]) <= Decimal(day["projected"]) <= Decimal(day["high"])

    # End-of-month projections
    assert "projected_end_balance" in forecast
    assert "projected_end_low" in forecast
    assert "projected_end_high" in forecast
    assert Decimal(forecast["projected_end_low"]) <= Decimal(forecast["projected_end_balance"])
    assert Decimal(forecast["projected_end_balance"]) <= Decimal(forecast["projected_end_high"])

    # 4. Verify confidence
    assert forecast["confidence"] in ("low", "medium", "high")
    # With 60 days of data and 1 recurring pattern, should be at least medium
    assert forecast["confidence"] in ("medium", "high")

    # 5. Verify confidence inputs exposed
    ci = forecast["confidence_inputs"]
    assert "days_of_transaction_data" in ci
    assert "total_recurring_patterns" in ci

    # 6. Verify assumptions present and explicit
    assumptions = forecast["assumptions"]
    assert isinstance(assumptions, list)
    assert len(assumptions) >= 3
    # Must mention balance
    assert any("balance" in a.lower() for a in assumptions)
    # Must mention spending
    assert any("spending" in a.lower() for a in assumptions)

    # 7. Verify urgency
    assert isinstance(forecast["urgency_score"], int)
    assert 0 <= forecast["urgency_score"] <= 100
    assert "factors" in forecast["urgency_factors"]

    # 8. Get latest forecast
    resp = await client.get("/forecast/latest", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == forecast["id"]

    # 9. Get summary
    resp = await client.get("/forecast/summary", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["safe_to_spend_today"] == forecast["safe_to_spend_today"]
    assert "daily_balances" not in summary

    # 10. Compute another forecast, check history
    await client.post("/forecast/compute", headers=headers)
    resp = await client.get("/forecast/history", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # 11. Seed cheat codes + compute Top 3 with urgency influence
    await client.post("/cheat-codes/seed", headers=headers)
    resp = await client.post("/cheat-codes/top-3", headers=headers)
    assert resp.status_code == 200
    top3 = resp.json()
    assert len(top3) == 3

    # 12. Verify confidence rules NEVER violated regardless of urgency
    for r in top3:
        assert r["confidence"] != "low"  # PRD absolute rule
        assert len(r["explanation"]) > 0
    assert any(r["is_quick_win"] for r in top3)
