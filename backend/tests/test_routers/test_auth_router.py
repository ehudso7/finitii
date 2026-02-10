import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_endpoint(client: AsyncClient):
    """POST /auth/register creates user, returns 201."""
    response = await client.post(
        "/auth/register",
        json={"email": "router@example.com", "password": "SecurePass123!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "router@example.com"
    assert data["status"] == "active"
    assert "id" in data


@pytest.mark.asyncio
async def test_login_endpoint(client: AsyncClient):
    """POST /auth/login returns token."""
    await client.post(
        "/auth/register",
        json={"email": "login-r@example.com", "password": "Pass123!"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "login-r@example.com", "password": "Pass123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """POST /auth/login with wrong password returns 401."""
    await client.post(
        "/auth/register",
        json={"email": "wrongpw-r@example.com", "password": "Pass123!"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": "wrongpw-r@example.com", "password": "WrongPass123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_endpoint(client: AsyncClient):
    """POST /auth/logout revokes session, returns 204."""
    await client.post(
        "/auth/register",
        json={"email": "logout-r@example.com", "password": "Pass123!"},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "logout-r@example.com", "password": "Pass123!"},
    )
    token = login_resp.json()["token"]

    response = await client.post(
        "/auth/logout",
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 204

    # After logout, authenticated request should fail
    response = await client.get(
        "/consent/status",
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client: AsyncClient):
    """Request without token returns 401."""
    response = await client.get("/consent/status")
    assert response.status_code == 401
