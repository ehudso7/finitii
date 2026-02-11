"""Phase 4 router tests: forecast endpoints."""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.user import User


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p4router@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p4router@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


async def _create_account(db_session: AsyncSession, user_id: str):
    """Create a checking account directly in DB for the test user."""
    import uuid
    acct = Account(
        user_id=uuid.UUID(user_id),
        account_type=AccountType.checking,
        institution_name="Test Bank",
        account_name="Checking",
        current_balance=Decimal("2500.00"),
        available_balance=Decimal("2500.00"),
    )
    db_session.add(acct)
    await db_session.flush()
    return acct


# --- Compute ---

@pytest.mark.asyncio
async def test_compute_forecast(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)
    await _create_account(db_session, user_id)

    resp = await client.post("/forecast/compute", headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    assert "safe_to_spend_today" in data
    assert "safe_to_spend_week" in data
    assert "daily_balances" in data
    assert len(data["daily_balances"]) == 30
    assert "projected_end_balance" in data
    assert "projected_end_low" in data
    assert "projected_end_high" in data
    assert "confidence" in data
    assert "confidence_inputs" in data
    assert "assumptions" in data
    assert isinstance(data["assumptions"], list)
    assert "urgency_score" in data
    assert "urgency_factors" in data
    assert "computed_at" in data


@pytest.mark.asyncio
async def test_compute_forecast_no_account(client: AsyncClient, db_session: AsyncSession):
    """Forecast works even with no accounts (balance = 0)."""
    headers, _ = await _register_and_login(client)

    resp = await client.post("/forecast/compute", headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert Decimal(data["safe_to_spend_today"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_compute_forecast_unauthenticated(client: AsyncClient, db_session: AsyncSession):
    """Forecast requires authentication."""
    resp = await client.post("/forecast/compute")
    assert resp.status_code in (401, 403)


# --- Latest ---

@pytest.mark.asyncio
async def test_get_latest_forecast(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)
    await _create_account(db_session, user_id)

    # Compute first
    await client.post("/forecast/compute", headers=headers)

    # Get latest
    resp = await client.get("/forecast/latest", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "safe_to_spend_today" in data
    assert "daily_balances" in data


@pytest.mark.asyncio
async def test_get_latest_forecast_none(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/forecast/latest", headers=headers)
    assert resp.status_code == 404


# --- Summary ---

@pytest.mark.asyncio
async def test_get_forecast_summary(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)
    await _create_account(db_session, user_id)

    await client.post("/forecast/compute", headers=headers)

    resp = await client.get("/forecast/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    # Summary should have the key fields but NOT daily_balances
    assert "safe_to_spend_today" in data
    assert "safe_to_spend_week" in data
    assert "projected_end_balance" in data
    assert "confidence" in data
    assert "urgency_score" in data
    # Summary model does NOT include daily_balances
    assert "daily_balances" not in data


@pytest.mark.asyncio
async def test_get_summary_no_forecast(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/forecast/summary", headers=headers)
    assert resp.status_code == 404


# --- History ---

@pytest.mark.asyncio
async def test_get_forecast_history(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)
    await _create_account(db_session, user_id)

    # Compute 3 forecasts
    await client.post("/forecast/compute", headers=headers)
    await client.post("/forecast/compute", headers=headers)
    await client.post("/forecast/compute", headers=headers)

    resp = await client.get("/forecast/history?limit=2", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_forecast_history_empty(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/forecast/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_forecast_history_bad_limit(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/forecast/history?limit=0", headers=headers)
    assert resp.status_code == 400

    resp = await client.get("/forecast/history?limit=100", headers=headers)
    assert resp.status_code == 400
