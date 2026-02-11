"""Phase 5 end-to-end integration test.

Full flow: create manual bills → list bills (confidence visible) →
toggle essential → compute forecast (manual bills in STS) →
compute Top 3 (essential suppressed) → bill summary → deactivate.
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p5e2e@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p5e2e@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


def _future(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_phase5_full_bills_flow(client: AsyncClient, db_session: AsyncSession):
    """End-to-end: bills, essential toggle, forecast integration, ranking."""
    headers, user_id = await _register_and_login(client)

    # Create a checking account for forecast
    acct = Account(
        user_id=uuid.UUID(user_id),
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Checking",
        current_balance=Decimal("5000.00"),
        available_balance=Decimal("5000.00"),
    )
    db_session.add(acct)
    await db_session.flush()

    # 1. Create manual bills
    resp = await client.post("/bills", json={
        "label": "Rent", "estimated_amount": "1500.00",
        "frequency": "monthly", "next_expected_date": _future(3),
        "is_essential": True,
    }, headers=headers)
    assert resp.status_code == 201
    rent_id = resp.json()["id"]

    resp = await client.post("/bills", json={
        "label": "Netflix", "estimated_amount": "15.99",
        "frequency": "monthly", "next_expected_date": _future(10),
    }, headers=headers)
    assert resp.status_code == 201
    netflix_id = resp.json()["id"]

    resp = await client.post("/bills", json={
        "label": "Gym", "estimated_amount": "50.00",
        "frequency": "monthly", "next_expected_date": _future(5),
    }, headers=headers)
    assert resp.status_code == 201
    gym_id = resp.json()["id"]

    # 2. List bills — confidence always visible
    resp = await client.get("/bills", headers=headers)
    assert resp.status_code == 200
    bills = resp.json()
    assert len(bills) == 3
    for bill in bills:
        assert "confidence" in bill
        assert bill["confidence"] == "high"  # Manual bills = high confidence
        assert "is_essential" in bill
        assert "is_manual" in bill
        assert bill["is_manual"] is True

    # 3. Verify essential flag
    rent_bill = next(b for b in bills if b["id"] == rent_id)
    assert rent_bill["is_essential"] is True
    netflix_bill = next(b for b in bills if b["id"] == netflix_id)
    assert netflix_bill["is_essential"] is False

    # 4. Toggle Netflix to essential
    resp = await client.post(
        f"/bills/{netflix_id}/essential",
        json={"is_essential": True},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_essential"] is True

    # 5. Compute forecast — manual bills feed STS
    resp = await client.post("/forecast/compute", headers=headers)
    assert resp.status_code == 201
    forecast = resp.json()

    # Rent ($1500 due in 3 days) + Gym ($50 due in 5 days) should reduce STS week
    sts_week = Decimal(forecast["safe_to_spend_week"])
    assert sts_week < Decimal("5000.00")
    # Rent + Gym are within 7 days = $1550 reduction
    assert sts_week <= Decimal("3500.00")

    # Netflix is due in 10 days, so NOT in STS week
    # But might be in 30-day projection

    # 6. Seed cheat codes and compute Top 3
    await client.post("/cheat-codes/seed", headers=headers)
    resp = await client.post("/cheat-codes/top-3", headers=headers)
    assert resp.status_code == 200
    top3 = resp.json()
    assert len(top3) == 3

    # Confidence rules still hold
    for r in top3:
        assert r["confidence"] != "low"
    assert any(r["is_quick_win"] for r in top3)

    # 7. Bill summary
    resp = await client.get("/bills/summary", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_bills"] == 3
    assert summary["essential_count"] == 2  # Rent + Netflix
    assert summary["manual_count"] == 3
    assert Decimal(summary["total_monthly_estimate"]) > Decimal("1500.00")

    # 8. Update gym bill
    resp = await client.put(
        f"/bills/{gym_id}",
        json={"label": "Gym Membership", "estimated_amount": "60.00"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "Gym Membership"
    assert Decimal(resp.json()["estimated_amount"]) == Decimal("60.00")

    # 9. Deactivate Netflix
    resp = await client.delete(f"/bills/{netflix_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # 10. Verify deactivated bill no longer in list
    resp = await client.get("/bills", headers=headers)
    assert len(resp.json()) == 2

    # 11. Recompute forecast — Netflix should not affect STS anymore
    resp = await client.post("/forecast/compute", headers=headers)
    assert resp.status_code == 201

    # 12. Final summary
    resp = await client.get("/bills/summary", headers=headers)
    assert resp.json()["total_bills"] == 2
    assert resp.json()["essential_count"] == 1  # Only Rent now
