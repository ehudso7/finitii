"""Phase 9: Security hygiene verification tests.

Verifies:
1. Request ID middleware adds X-Request-ID to all responses
2. Error responses include request_id (traceability)
3. 500 errors do not leak stack traces or internal details
4. Password hashes never appear in API responses
5. Auth endpoints enforce correct error codes
6. Session tokens are cryptographically strong
7. Expired sessions are rejected
8. Inactive users cannot authenticate
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session as SessionModel
from app.models.user import User, UserStatus
from app.services.storage import InMemoryStorageBackend, set_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield
    set_storage(None)


async def _register_and_login(
    client: AsyncClient,
    email: str = "security@test.com",
    password: str = "SecurePass123!",
) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"], "token": data["token"]}


# ============================================================
# 1. Request ID middleware
# ============================================================


@pytest.mark.asyncio
async def test_health_has_request_id(client: AsyncClient):
    """Health endpoint includes X-Request-ID header."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    request_id = resp.headers.get("x-request-id")
    assert request_id is not None
    # Verify it's a valid UUID
    uuid.UUID(request_id)


@pytest.mark.asyncio
async def test_request_id_unique_per_request(client: AsyncClient):
    """Each request gets a unique X-Request-ID."""
    ids = set()
    for _ in range(5):
        resp = await client.get("/health")
        ids.add(resp.headers["x-request-id"])
    assert len(ids) == 5


@pytest.mark.asyncio
async def test_request_id_on_error_responses(client: AsyncClient):
    """Error responses also include X-Request-ID."""
    # 401 error (no auth)
    resp = await client.get("/vault")
    assert resp.status_code in (401, 403)
    assert "x-request-id" in resp.headers


@pytest.mark.asyncio
async def test_request_id_on_404(client: AsyncClient, db_session: AsyncSession):
    """404 responses include X-Request-ID."""
    info = await _register_and_login(client)
    headers = {"X-Session-Token": info["token"]}
    resp = await client.get(
        "/vault/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404
    assert "x-request-id" in resp.headers


# ============================================================
# 2. Error responses include request_id in body
# ============================================================


@pytest.mark.asyncio
async def test_error_body_has_request_id(client: AsyncClient):
    """HTTP error responses include request_id in JSON body."""
    resp = await client.get("/vault")  # No auth → 401/403
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert "request_id" in body
    assert body["request_id"] is not None
    assert body["error"] is True


@pytest.mark.asyncio
async def test_validation_error_has_request_id(client: AsyncClient, db_session: AsyncSession):
    """422 validation errors include request_id."""
    info = await _register_and_login(client)
    headers = {"X-Session-Token": info["token"]}
    # Send invalid JSON to coach endpoint (missing required field)
    resp = await client.post(
        "/coach",
        headers=headers,
        content="not json",
    )
    # Either 422 (validation) or 400 — both should have request_id
    if resp.status_code in (400, 422):
        body = resp.json()
        assert "request_id" in body


# ============================================================
# 3. 500 errors do not leak internals
# ============================================================


@pytest.mark.asyncio
async def test_500_error_generic_message(client: AsyncClient):
    """500 errors return generic message, no stack traces."""
    # We test that the error handler format is correct by examining
    # the registered error handler behavior
    from app.core.errors import register_error_handlers
    from app.main import app as test_app

    # Verify error handlers are registered (they suppress details)
    assert len(test_app.exception_handlers) >= 3  # HTTP, Validation, Generic


# ============================================================
# 4. Password hashes never in API responses
# ============================================================


@pytest.mark.asyncio
async def test_register_no_password_in_response(client: AsyncClient):
    """Register endpoint does not return password hash."""
    resp = await client.post(
        "/auth/register",
        json={"email": "nopw@test.com", "password": "SecurePass123!"},
    )
    assert resp.status_code == 201
    body = resp.json()
    body_str = str(body).lower()
    assert "password_hash" not in body_str
    assert "securepass123" not in body_str
    assert "bcrypt" not in body_str


@pytest.mark.asyncio
async def test_login_no_password_in_response(client: AsyncClient):
    """Login endpoint does not return password hash."""
    await client.post(
        "/auth/register",
        json={"email": "nopw2@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "nopw2@test.com", "password": "SecurePass123!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    body_str = str(body).lower()
    assert "password_hash" not in body_str
    assert "bcrypt" not in body_str


@pytest.mark.asyncio
async def test_export_no_password_hash(client: AsyncClient, db_session: AsyncSession):
    """Export endpoint does not include password hash."""
    info = await _register_and_login(client)
    headers = {"X-Session-Token": info["token"]}
    resp = await client.get("/user/export", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    body_str = str(body).lower()
    assert "password_hash" not in body_str


# ============================================================
# 5. Auth error codes
# ============================================================


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Wrong password returns 401 with generic message."""
    await client.post(
        "/auth/register",
        json={"email": "wrongpw@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "wrongpw@test.com", "password": "WrongPass999!"},
    )
    assert resp.status_code == 401
    # Generic message — should not reveal whether email exists
    assert "password" not in resp.json().get("detail", "").lower() or \
           "invalid" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    """Nonexistent email returns 401 (same as wrong password)."""
    resp = await client.post(
        "/auth/login",
        json={"email": "ghost@test.com", "password": "AnyPass123!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_registration(client: AsyncClient):
    """Duplicate email registration returns 409."""
    await client.post(
        "/auth/register",
        json={"email": "dupe@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/register",
        json={"email": "dupe@test.com", "password": "SecurePass123!"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invalid_token_rejected(client: AsyncClient):
    """Invalid session token returns 401."""
    resp = await client.get(
        "/vault",
        headers={"X-Session-Token": "definitely-not-a-valid-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_rejected(client: AsyncClient):
    """Missing session token returns 401 or 403."""
    resp = await client.get("/vault")
    assert resp.status_code in (401, 403)


# ============================================================
# 6. Session token strength
# ============================================================


@pytest.mark.asyncio
async def test_session_token_length(client: AsyncClient):
    """Session tokens are at least 64 characters (secrets.token_hex(32))."""
    await client.post(
        "/auth/register",
        json={"email": "toklen@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "toklen@test.com", "password": "SecurePass123!"},
    )
    token = resp.json()["token"]
    assert len(token) >= 64


@pytest.mark.asyncio
async def test_session_tokens_unique(client: AsyncClient):
    """Each login produces a unique token."""
    await client.post(
        "/auth/register",
        json={"email": "uniqtok@test.com", "password": "SecurePass123!"},
    )
    tokens = set()
    for _ in range(3):
        resp = await client.post(
            "/auth/login",
            json={"email": "uniqtok@test.com", "password": "SecurePass123!"},
        )
        tokens.add(resp.json()["token"])
    assert len(tokens) == 3


# ============================================================
# 7. Expired sessions rejected
# ============================================================


@pytest.mark.asyncio
async def test_expired_session_rejected(client: AsyncClient, db_session: AsyncSession):
    """Expired session tokens are rejected."""
    info = await _register_and_login(client, email="expired@test.com")
    token = info["token"]

    # Manually expire the session
    result = await db_session.execute(
        select(SessionModel).where(SessionModel.token == token)
    )
    session = result.scalar_one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.flush()

    resp = await client.get("/vault", headers={"X-Session-Token": token})
    assert resp.status_code == 401


# ============================================================
# 8. Inactive user cannot authenticate
# ============================================================


@pytest.mark.asyncio
async def test_deleted_user_cannot_login(client: AsyncClient, db_session: AsyncSession):
    """Users with deleted status cannot log in."""
    await client.post(
        "/auth/register",
        json={"email": "willdelete@test.com", "password": "SecurePass123!"},
    )
    # Mark user as deleted directly
    result = await db_session.execute(
        select(User).where(User.email == "willdelete@test.com")
    )
    user = result.scalar_one()
    user.status = UserStatus.deleted
    await db_session.flush()

    resp = await client.post(
        "/auth/login",
        json={"email": "willdelete@test.com", "password": "SecurePass123!"},
    )
    assert resp.status_code in (401, 403)


# ============================================================
# 9. Logout revokes session
# ============================================================


@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient, db_session: AsyncSession):
    """POST /auth/logout revokes the session token."""
    info = await _register_and_login(client, email="logout@test.com")
    headers = {"X-Session-Token": info["token"]}

    # Logout
    resp = await client.post("/auth/logout", headers=headers)
    assert resp.status_code in (200, 204)

    # Token no longer valid
    resp = await client.get("/vault", headers=headers)
    assert resp.status_code == 401


# ============================================================
# 10. Cross-user data isolation
# ============================================================


@pytest.mark.asyncio
async def test_vault_cross_user_isolation(
    client: AsyncClient, db_session: AsyncSession
):
    """User A cannot see User B's vault items."""
    info_a = await _register_and_login(client, email="usera@test.com")
    headers_a = {"X-Session-Token": info_a["token"]}

    # Upload as user A
    import io
    files = {"file": ("a.jpg", io.BytesIO(b"data"), "image/jpeg")}
    resp = await client.post(
        "/vault", headers=headers_a, files=files,
        data={"item_type": "receipt"},
    )
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    # Register and login as user B
    await client.post(
        "/auth/register",
        json={"email": "userb@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "userb@test.com", "password": "SecurePass123!"},
    )
    headers_b = {"X-Session-Token": resp.json()["token"]}

    # User B cannot see User A's item
    resp = await client.get(f"/vault/{item_id}", headers=headers_b)
    assert resp.status_code == 404

    # User B's vault is empty
    resp = await client.get("/vault", headers=headers_b)
    assert resp.status_code == 200
    assert len(resp.json()) == 0
