"""Integration tests for Money Graph API routers.

All endpoints return derived views only — no raw provider data leaked.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import category_service


async def _auth(client: AsyncClient, email: str = "mg@example.com") -> str:
    """Register + login, return token."""
    await client.post(
        "/auth/register",
        json={"email": email, "password": "Pass1234!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": "Pass1234!"},
    )
    return resp.json()["token"]


async def _seed_categories(db_session: AsyncSession):
    await category_service.seed_system_categories(db_session)
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_and_list_accounts(client: AsyncClient, db_session: AsyncSession):
    token = await _auth(client, "acct-rt@example.com")
    headers = {"X-Session-Token": token}

    # Create manual account
    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Main",
            "current_balance": "1500.00",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["institution_name"] == "Chase"
    assert data["current_balance"] == "1500.00"
    assert "connection_id" not in data  # No raw provider IDs
    account_id = data["id"]

    # List accounts
    resp = await client.get("/accounts", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_update_balance(client: AsyncClient, db_session: AsyncSession):
    token = await _auth(client, "bal-rt@example.com")
    headers = {"X-Session-Token": token}

    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "BoA",
            "account_name": "Checking",
            "current_balance": "1000.00",
        },
        headers=headers,
    )
    account_id = resp.json()["id"]

    resp = await client.patch(
        f"/accounts/{account_id}/balance",
        json={"current_balance": "1200.00"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["current_balance"] == "1200.00"


@pytest.mark.asyncio
async def test_create_and_list_transactions(client: AsyncClient, db_session: AsyncSession):
    await _seed_categories(db_session)
    token = await _auth(client, "txn-rt@example.com")
    headers = {"X-Session-Token": token}

    # Create account first
    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Main",
            "current_balance": "5000.00",
        },
        headers=headers,
    )
    account_id = resp.json()["id"]

    # Create transaction
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "raw_description": "STARBUCKS #1234 NYC",
            "amount": "5.75",
            "transaction_type": "debit",
            "transaction_date": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["merchant_name"] == "Starbucks"
    assert data["category_name"] == "Dining"
    assert "provider_transaction_id" not in data  # No raw data

    # List transactions
    resp = await client.get("/transactions", headers=headers)
    assert resp.status_code == 200
    txns = resp.json()
    assert len(txns) == 1


@pytest.mark.asyncio
async def test_recategorize_transaction(client: AsyncClient, db_session: AsyncSession):
    await _seed_categories(db_session)
    token = await _auth(client, "recat-rt@example.com")
    headers = {"X-Session-Token": token}

    # Create account + transaction
    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Main",
            "current_balance": "5000.00",
        },
        headers=headers,
    )
    account_id = resp.json()["id"]

    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "raw_description": "STARBUCKS #1",
            "amount": "5.00",
            "transaction_type": "debit",
            "transaction_date": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )
    txn_id = resp.json()["id"]

    # Get groceries category ID
    cats = await category_service.get_system_categories(db_session)
    groceries = next(c for c in cats if c.name == "Groceries")

    # Recategorize
    resp = await client.patch(
        f"/transactions/{txn_id}/category",
        json={"category_id": str(groceries.id)},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["category_name"] == "Groceries"


@pytest.mark.asyncio
async def test_detect_and_list_recurring(client: AsyncClient, db_session: AsyncSession):
    await _seed_categories(db_session)
    token = await _auth(client, "recur-rt@example.com")
    headers = {"X-Session-Token": token}

    # Create account
    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Main",
            "current_balance": "5000.00",
        },
        headers=headers,
    )
    account_id = resp.json()["id"]

    # Add 4 monthly Netflix transactions
    base_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
    for i in range(4):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"NETFLIX #{i}",
                "amount": "15.99",
                "transaction_type": "debit",
                "transaction_date": (base_date + timedelta(days=30 * i)).isoformat(),
            },
            headers=headers,
        )

    # Detect
    resp = await client.post("/recurring/detect", headers=headers)
    assert resp.status_code == 200
    patterns = resp.json()
    assert len(patterns) >= 1

    p = patterns[0]
    assert "confidence" in p
    assert "assumptions" in p
    assert "merchant_name" in p
    assert "merchant_id" not in p  # No raw IDs

    # List
    resp = await client.get("/recurring", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_money_graph_summary(client: AsyncClient, db_session: AsyncSession):
    await _seed_categories(db_session)
    token = await _auth(client, "summary-rt@example.com")
    headers = {"X-Session-Token": token}

    # Create account
    await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Main",
            "current_balance": "3000.00",
        },
        headers=headers,
    )

    resp = await client.get("/money-graph/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_balance" in data
    assert "monthly_income" in data
    assert "monthly_spending" in data
    assert "top_categories" in data
    assert "top_merchants" in data
    assert "assumptions" in data
