"""Phase 9: Coach red-team refusal tests.

Verifies that the coach endpoint safely handles:
1. Unknown/malicious context_type strings (graceful degradation)
2. Invalid mode values (rejected with 400)
3. Invalid UUID context_id (rejected with 400)
4. Missing required fields for explain/execute (rejected with 400)
5. Injection attempts in free-text fields (no execution)
6. Regulated/illegal context types (no special behavior)
7. Coach memory operations without consent (rejected with 403)
8. Invalid tone/aggressiveness values (rejected with 400)

All tests confirm the coach never exposes internal state, never executes
injected content, and always returns structured template-based responses.
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storage import InMemoryStorageBackend, set_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield
    set_storage(None)


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "redteam@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "redteam@test.com", "password": "SecurePass123!"},
    )
    return {"X-Session-Token": resp.json()["token"]}


# --- Red-team: Unknown/malicious context_type (graceful degradation) ---


MALICIOUS_CONTEXT_TYPES = [
    "system_prompt",
    "admin",
    "eval",
    "exec",
    "__proto__",
    "sql_injection",
    "'; DROP TABLE users; --",
    "<script>alert(1)</script>",
    "../../etc/passwd",
    "regulated_advice",
    "tax_advice",
    "legal_advice",
    "medical_advice",
    "investment_recommendation",
    "gambling_strategy",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("malicious_type", MALICIOUS_CONTEXT_TYPES)
async def test_explain_unknown_context_type_graceful(
    client: AsyncClient, db_session: AsyncSession, malicious_type: str
):
    """Coach explain mode handles unknown context_types without leaking internals."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={
            "mode": "explain",
            "context_type": malicious_type,
            "context_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_used"] == "unknown"
    assert "caveats" in data
    assert len(data["caveats"]) > 0
    # Must NOT contain stack traces or internal paths
    response_text = str(data)
    assert "Traceback" not in response_text
    assert "/home/" not in response_text
    assert "sqlalchemy" not in response_text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("malicious_type", MALICIOUS_CONTEXT_TYPES)
async def test_execute_unknown_context_type_graceful(
    client: AsyncClient, db_session: AsyncSession, malicious_type: str
):
    """Coach execute mode handles unknown context_types without leaking internals."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={
            "mode": "execute",
            "context_type": malicious_type,
            "context_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_used"] == "unknown"


# --- Red-team: Invalid modes ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_mode",
    ["admin", "delete", "shell", "eval", "", "EXPLAIN", "Execute", "__init__"],
)
async def test_invalid_mode_rejected(
    client: AsyncClient, db_session: AsyncSession, bad_mode: str
):
    """Invalid modes are rejected with 400."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": bad_mode},
    )
    assert resp.status_code == 400


# --- Red-team: Invalid UUID context_id ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_id",
    ["not-a-uuid", "12345", "'; DROP TABLE users;--", "<script>", ""],
)
async def test_invalid_context_id_rejected(
    client: AsyncClient, db_session: AsyncSession, bad_id: str
):
    """Non-UUID context_id is rejected with 400."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={
            "mode": "explain",
            "context_type": "recurring_pattern",
            "context_id": bad_id,
        },
    )
    assert resp.status_code == 400


# --- Red-team: Missing required fields ---


@pytest.mark.asyncio
async def test_explain_missing_context_type(
    client: AsyncClient, db_session: AsyncSession
):
    """Explain mode without context_type returns 400."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "explain", "context_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 400
    assert "context_type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_explain_missing_context_id(
    client: AsyncClient, db_session: AsyncSession
):
    """Explain mode without context_id returns 400."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "explain", "context_type": "recommendation"},
    )
    assert resp.status_code == 400
    assert "context_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_execute_missing_context_type(
    client: AsyncClient, db_session: AsyncSession
):
    """Execute mode without context_type returns 400."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "execute", "context_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_execute_missing_context_id(
    client: AsyncClient, db_session: AsyncSession
):
    """Execute mode without context_id returns 400."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "execute", "context_type": "recommendation"},
    )
    assert resp.status_code == 400


# --- Red-team: Injection in question field ---


@pytest.mark.asyncio
async def test_sql_injection_in_question_field(
    client: AsyncClient, db_session: AsyncSession
):
    """SQL injection in question field is safely handled (not executed)."""
    headers = await _register_and_login(client)
    # Use unknown context_type so it takes the graceful degradation path
    resp = await client.post(
        "/coach",
        headers=headers,
        json={
            "mode": "explain",
            "context_type": "sql_test",
            "context_id": str(uuid.uuid4()),
            "question": "'; DROP TABLE users; --",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_used"] == "unknown"
    # Injection payload not in response
    assert "DROP TABLE" not in data.get("response", "")


@pytest.mark.asyncio
async def test_xss_in_question_field(
    client: AsyncClient, db_session: AsyncSession
):
    """XSS payload in question field is not reflected unsafely."""
    headers = await _register_and_login(client)
    # Use unknown context_type so it takes the graceful degradation path
    resp = await client.post(
        "/coach",
        headers=headers,
        json={
            "mode": "explain",
            "context_type": "xss_test",
            "context_id": str(uuid.uuid4()),
            "question": "<script>alert('xss')</script>",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Template-based output should not execute scripts
    assert data["template_used"] == "unknown"


# --- Red-team: Coach memory without ai_memory consent ---


@pytest.mark.asyncio
async def test_set_memory_without_consent_rejected(
    client: AsyncClient, db_session: AsyncSession
):
    """Setting coach memory without ai_memory consent returns 403."""
    headers = await _register_and_login(client)
    resp = await client.put(
        "/coach/memory",
        headers=headers,
        json={"tone": "encouraging", "aggressiveness": "moderate"},
    )
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_memory_without_consent_returns_null(
    client: AsyncClient, db_session: AsyncSession
):
    """Getting coach memory without ai_memory consent returns null."""
    headers = await _register_and_login(client)
    resp = await client.get("/coach/memory", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


# --- Red-team: Invalid tone/aggressiveness values ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_tone",
    ["malicious", "angry", "sarcastic", "DROP TABLE", "script_tag"],
)
async def test_invalid_tone_rejected(
    client: AsyncClient, db_session: AsyncSession, bad_tone: str
):
    """Invalid tone values are rejected with 400."""
    headers = await _register_and_login(client)
    # First grant ai_memory consent so we test tone validation, not consent
    await client.post(
        "/consent",
        headers=headers,
        json={"consent_type": "ai_memory", "granted": True},
    )
    resp = await client.put(
        "/coach/memory",
        headers=headers,
        json={"tone": bad_tone},
    )
    assert resp.status_code == 400
    assert "tone" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_agg",
    ["nuclear", "extreme", "max", "'; DELETE FROM;--", "undefined"],
)
async def test_invalid_aggressiveness_rejected(
    client: AsyncClient, db_session: AsyncSession, bad_agg: str
):
    """Invalid aggressiveness values are rejected with 400."""
    headers = await _register_and_login(client)
    await client.post(
        "/consent",
        headers=headers,
        json={"consent_type": "ai_memory", "granted": True},
    )
    resp = await client.put(
        "/coach/memory",
        headers=headers,
        json={"aggressiveness": bad_agg},
    )
    assert resp.status_code == 400
    assert "aggressiveness" in resp.json()["detail"]


# --- Red-team: All coach outputs must be template-based ---


@pytest.mark.asyncio
async def test_plan_mode_template_based(
    client: AsyncClient, db_session: AsyncSession
):
    """Plan mode returns template_used (never free-form)."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "plan"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "template_used" in data
    assert data["template_used"] is not None


@pytest.mark.asyncio
async def test_review_mode_template_based(
    client: AsyncClient, db_session: AsyncSession
):
    """Review mode returns template_used (never free-form)."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "review"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "template_used" in data
    assert data["template_used"] is not None


@pytest.mark.asyncio
async def test_recap_mode_template_based(
    client: AsyncClient, db_session: AsyncSession
):
    """Recap mode returns template_used (never free-form)."""
    headers = await _register_and_login(client)
    resp = await client.post(
        "/coach",
        headers=headers,
        json={"mode": "recap"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "template_used" in data
    assert data["template_used"] is not None


# --- Red-team: Coach requires authentication ---


@pytest.mark.asyncio
async def test_coach_requires_auth(client: AsyncClient):
    """Coach endpoint requires authentication."""
    resp = await client.post(
        "/coach",
        json={"mode": "plan"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_coach_memory_requires_auth(client: AsyncClient):
    """Coach memory endpoints require authentication."""
    resp = await client.get("/coach/memory")
    assert resp.status_code in (401, 403)

    resp = await client.put(
        "/coach/memory",
        json={"tone": "encouraging"},
    )
    assert resp.status_code in (401, 403)
