import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str = "consent-r@example.com") -> str:
    """Helper: register + login, return token."""
    await client.post(
        "/auth/register",
        json={"email": email, "password": "Pass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": "Pass123!"},
    )
    return resp.json()["token"]


@pytest.mark.asyncio
async def test_grant_consent(client: AsyncClient):
    """POST /consent/grant grants consent."""
    token = await _register_and_login(client, "grant-r@example.com")
    response = await client.post(
        "/consent/grant",
        json={"consent_type": "data_access"},
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["granted"] is True
    assert data["consent_type"] == "data_access"


@pytest.mark.asyncio
async def test_revoke_consent(client: AsyncClient):
    """POST /consent/revoke revokes consent."""
    token = await _register_and_login(client, "revoke-r@example.com")
    await client.post(
        "/consent/grant",
        json={"consent_type": "data_access"},
        headers={"X-Session-Token": token},
    )
    response = await client.post(
        "/consent/revoke",
        json={"consent_type": "data_access"},
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["granted"] is False
    assert data["revoked_at"] is not None


@pytest.mark.asyncio
async def test_consent_status(client: AsyncClient):
    """GET /consent/status returns all consent states."""
    token = await _register_and_login(client, "status-r@example.com")
    response = await client.get(
        "/consent/status",
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 200
    data = response.json()
    consents = data["consents"]
    # All should be False by default
    assert consents["data_access"] is False
    assert consents["ai_memory"] is False
    assert consents["terms_of_service"] is False


@pytest.mark.asyncio
async def test_invalid_consent_type(client: AsyncClient):
    """POST /consent/grant with invalid consent_type returns 400."""
    token = await _register_and_login(client, "invalid-r@example.com")
    response = await client.post(
        "/consent/grant",
        json={"consent_type": "invalid_type"},
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 400
