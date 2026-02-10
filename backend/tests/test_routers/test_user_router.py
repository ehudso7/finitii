import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str = "user-r@example.com") -> str:
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
async def test_export_endpoint(client: AsyncClient):
    """GET /user/export returns user data."""
    token = await _register_and_login(client, "export-r@example.com")

    # Grant a consent first
    await client.post(
        "/consent/grant",
        json={"consent_type": "data_access"},
        headers={"X-Session-Token": token},
    )

    response = await client.get(
        "/user/export",
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "consent_records" in data
    assert "audit_log" in data
    assert data["user"]["email"] == "export-r@example.com"
    assert len(data["consent_records"]) == 1


@pytest.mark.asyncio
async def test_delete_endpoint(client: AsyncClient):
    """DELETE /user/delete deletes account, subsequent auth fails."""
    token = await _register_and_login(client, "delete-r@example.com")

    response = await client.delete(
        "/user/delete",
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 204

    # After deletion, login should fail
    response = await client.post(
        "/auth/login",
        json={"email": "delete-r@example.com", "password": "Pass123!"},
    )
    # Either 401 (invalid credentials due to PII wipe) or 403 (inactive account)
    assert response.status_code in (401, 403)
