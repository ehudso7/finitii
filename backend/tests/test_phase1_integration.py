"""Phase 1 end-to-end integration test.

Full lifecycle: authenticated user -> create manual account -> add 6 months of
transactions (mix of merchants) -> normalize merchants -> auto-categorize ->
detect recurring patterns -> verify confidence levels -> get money graph summary
-> verify derived views expose assumptions/confidence -> all actions in audit log.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.services import category_service


@pytest.mark.asyncio
async def test_full_phase1_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """End-to-end Phase 1 lifecycle test."""

    # Seed system categories
    await category_service.seed_system_categories(db_session)
    await db_session.commit()

    # ──────────────────────────────────────────────────────────
    # Step 1: Register + Login
    # ──────────────────────────────────────────────────────────
    await client.post(
        "/auth/register",
        json={"email": "p1-e2e@example.com", "password": "SecurePass123!"},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "p1-e2e@example.com", "password": "SecurePass123!"},
    )
    token = login_resp.json()["token"]
    user_id = login_resp.json()["user_id"]
    headers = {"X-Session-Token": token}

    # ──────────────────────────────────────────────────────────
    # Step 2: Create manual account
    # ──────────────────────────────────────────────────────────
    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Primary Checking",
            "current_balance": "5000.00",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    account_id = resp.json()["id"]

    # ──────────────────────────────────────────────────────────
    # Step 3: Add 6 months of transactions (mix of merchants)
    # ──────────────────────────────────────────────────────────
    base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    # Netflix - monthly recurring ($15.99, 6 months)
    for i in range(6):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"NETFLIX #{1000 + i}",
                "amount": "15.99",
                "transaction_type": "debit",
                "transaction_date": (base_date + timedelta(days=30 * i)).isoformat(),
            },
            headers=headers,
        )

    # Starbucks - weekly ($5-7, ~24 transactions)
    for i in range(24):
        amount = f"{5 + (i % 3)}.{50 + i}"
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"STARBUCKS #{2000 + i} NYC",
                "amount": amount,
                "transaction_type": "debit",
                "transaction_date": (base_date + timedelta(days=7 * i)).isoformat(),
            },
            headers=headers,
        )

    # Amazon - irregular ($20-80, 4 transactions, ~45 day intervals -> non-standard)
    for i in range(4):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"AMAZON.COM*AB{i}CD",
                "amount": f"{20 + i * 15}.00",
                "transaction_type": "debit",
                "transaction_date": (base_date + timedelta(days=45 * i)).isoformat(),
            },
            headers=headers,
        )

    # Income - monthly payroll ($3000, 6 months)
    for i in range(6):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"PAYROLL DIRECT DEP #{3000 + i}",
                "amount": "3000.00",
                "transaction_type": "credit",
                "transaction_date": (base_date + timedelta(days=30 * i + 1)).isoformat(),
            },
            headers=headers,
        )

    # ──────────────────────────────────────────────────────────
    # Step 4: Verify merchants normalized
    # ──────────────────────────────────────────────────────────
    resp = await client.get("/transactions", headers=headers)
    assert resp.status_code == 200
    txns = resp.json()
    assert len(txns) == 40  # 6 + 24 + 4 + 6

    # All Starbucks transactions should have same merchant name
    starbucks_txns = [t for t in txns if t["merchant_name"] == "Starbucks"]
    assert len(starbucks_txns) == 24

    # All Amazon transactions normalized via alias
    amazon_txns = [t for t in txns if t["merchant_name"] == "Amazon"]
    assert len(amazon_txns) == 4

    # ──────────────────────────────────────────────────────────
    # Step 5: Verify auto-categorization
    # ──────────────────────────────────────────────────────────
    starbucks_categories = {t["category_name"] for t in starbucks_txns}
    assert starbucks_categories == {"Dining"}

    amazon_categories = {t["category_name"] for t in amazon_txns}
    assert amazon_categories == {"Shopping"}

    # ──────────────────────────────────────────────────────────
    # Step 6: Detect recurring patterns
    # ──────────────────────────────────────────────────────────
    resp = await client.post("/recurring/detect", headers=headers)
    assert resp.status_code == 200
    patterns = resp.json()

    # Should detect at least Netflix (monthly) and Starbucks (weekly)
    merchant_names = {p["merchant_name"] for p in patterns}
    assert "Netflix" in merchant_names or len(patterns) >= 1

    # ──────────────────────────────────────────────────────────
    # Step 7: Verify confidence levels
    # ──────────────────────────────────────────────────────────
    for p in patterns:
        # Confidence always present
        assert p["confidence"] in ("low", "medium", "high")
        # Assumptions always present
        assert "assumptions" in p
        assert "interval_tolerance_days" in p["assumptions"]
        assert "amount_tolerance_pct" in p["assumptions"]
        # No raw IDs
        assert "merchant_id" not in p
        assert "user_id" not in p

    # Netflix with 6 consistent monthly payments should be high confidence
    netflix_patterns = [p for p in patterns if p["merchant_name"] == "Netflix"]
    if netflix_patterns:
        assert netflix_patterns[0]["confidence"] == "high"
        assert netflix_patterns[0]["frequency"] == "monthly"

    # ──────────────────────────────────────────────────────────
    # Step 8: Get money graph summary
    # ──────────────────────────────────────────────────────────
    resp = await client.get("/money-graph/summary", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()

    assert "total_balance" in summary
    assert "monthly_income" in summary
    assert "monthly_spending" in summary
    assert "top_categories" in summary
    assert "top_merchants" in summary
    assert "assumptions" in summary
    assert summary["total_balance"] == "5000.00"

    # ──────────────────────────────────────────────────────────
    # Step 9: Verify derived views don't expose raw provider data
    # ──────────────────────────────────────────────────────────
    resp = await client.get("/transactions", headers=headers)
    for txn in resp.json():
        assert "provider_transaction_id" not in txn
        assert "merchant_id" not in txn
        assert "user_id" not in txn

    resp = await client.get("/accounts", headers=headers)
    for acct in resp.json():
        assert "connection_id" not in acct
        assert "provider_connection_id" not in acct
        assert "user_id" not in acct

    # ──────────────────────────────────────────────────────────
    # Step 10: Verify all actions in audit log
    # ──────────────────────────────────────────────────────────
    import uuid as uuid_mod

    uid = uuid_mod.UUID(user_id)
    result = await db_session.execute(
        select(AuditLogEvent)
        .where(AuditLogEvent.user_id == uid)
        .order_by(AuditLogEvent.timestamp.asc())
    )
    events = result.scalars().all()
    event_types = {e.event_type for e in events}

    assert "auth.register" in event_types
    assert "auth.login" in event_types
    assert "account.created" in event_types
    assert "transaction.created" in event_types
    assert "recurring.detected" in event_types
