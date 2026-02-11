"""Phase 5 router tests: bills endpoints."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p5router@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p5router@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


def _future_date(days: int = 5) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.isoformat()


# --- Create manual bill ---

@pytest.mark.asyncio
async def test_create_manual_bill(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/bills",
        json={
            "label": "Rent",
            "estimated_amount": "1500.00",
            "frequency": "monthly",
            "next_expected_date": _future_date(),
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "Rent"
    assert data["is_manual"] is True
    assert data["confidence"] == "high"
    assert Decimal(data["estimated_amount"]) == Decimal("1500.00")


@pytest.mark.asyncio
async def test_create_manual_bill_essential(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/bills",
        json={
            "label": "Mortgage",
            "estimated_amount": "2000.00",
            "frequency": "monthly",
            "next_expected_date": _future_date(),
            "is_essential": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["is_essential"] is True


@pytest.mark.asyncio
async def test_create_manual_bill_invalid_frequency(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/bills",
        json={
            "label": "Bad",
            "estimated_amount": "10.00",
            "frequency": "daily",
            "next_expected_date": _future_date(),
        },
        headers=headers,
    )
    assert resp.status_code == 400


# --- List bills ---

@pytest.mark.asyncio
async def test_list_bills(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    await client.post("/bills", json={
        "label": "Netflix", "estimated_amount": "15.99",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)
    await client.post("/bills", json={
        "label": "Gym", "estimated_amount": "50.00",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)

    resp = await client.get("/bills", headers=headers)
    assert resp.status_code == 200
    bills = resp.json()
    assert len(bills) == 2
    # Confidence visible on each
    for bill in bills:
        assert "confidence" in bill


# --- Get single bill ---

@pytest.mark.asyncio
async def test_get_bill(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    create_resp = await client.post("/bills", json={
        "label": "Spotify", "estimated_amount": "9.99",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)
    bill_id = create_resp.json()["id"]

    resp = await client.get(f"/bills/{bill_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["label"] == "Spotify"


@pytest.mark.asyncio
async def test_get_bill_not_found(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/bills/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404


# --- Toggle essential ---

@pytest.mark.asyncio
async def test_toggle_essential(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    create_resp = await client.post("/bills", json={
        "label": "Internet", "estimated_amount": "75.00",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)
    bill_id = create_resp.json()["id"]
    assert create_resp.json()["is_essential"] is False

    # Toggle on
    resp = await client.post(
        f"/bills/{bill_id}/essential",
        json={"is_essential": True},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_essential"] is True

    # Toggle off
    resp = await client.post(
        f"/bills/{bill_id}/essential",
        json={"is_essential": False},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_essential"] is False


# --- Update bill ---

@pytest.mark.asyncio
async def test_update_bill(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    create_resp = await client.post("/bills", json={
        "label": "Old Name", "estimated_amount": "100.00",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)
    bill_id = create_resp.json()["id"]

    resp = await client.put(
        f"/bills/{bill_id}",
        json={"label": "New Name", "estimated_amount": "150.00"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "New Name"
    assert Decimal(resp.json()["estimated_amount"]) == Decimal("150.00")


# --- Deactivate ---

@pytest.mark.asyncio
async def test_deactivate_bill(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    create_resp = await client.post("/bills", json={
        "label": "Cancel Me", "estimated_amount": "10.00",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)
    bill_id = create_resp.json()["id"]

    resp = await client.delete(f"/bills/{bill_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Should no longer appear in list
    list_resp = await client.get("/bills", headers=headers)
    assert len(list_resp.json()) == 0


# --- Summary ---

@pytest.mark.asyncio
async def test_bill_summary(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    await client.post("/bills", json={
        "label": "Netflix", "estimated_amount": "15.99",
        "frequency": "monthly", "next_expected_date": _future_date(),
        "is_essential": True,
    }, headers=headers)
    await client.post("/bills", json={
        "label": "Gym", "estimated_amount": "50.00",
        "frequency": "monthly", "next_expected_date": _future_date(),
    }, headers=headers)

    resp = await client.get("/bills/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_bills"] == 2
    assert Decimal(data["total_monthly_estimate"]) > Decimal("60.00")
    assert data["essential_count"] == 1
    assert data["manual_count"] == 2


@pytest.mark.asyncio
async def test_bill_summary_empty(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/bills/summary", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total_bills"] == 0
