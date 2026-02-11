"""Phase 6 router tests: coach plan, review, recap, and memory endpoints."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeDifficulty,
    CheatCodeCategory,
    CheatCodeRun,
    Recommendation,
    RunStatus,
)
from app.models.consent import ConsentRecord, ConsentType
from app.models.goal import Goal, GoalType, GoalPriority
from app.models.user import User


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p6coach@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p6coach@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


async def _grant_consent(db: AsyncSession, user_id: str, consent_type: ConsentType):
    import uuid as uuid_mod
    consent = ConsentRecord(
        user_id=uuid_mod.UUID(user_id),
        consent_type=consent_type,
        granted=True,
    )
    db.add(consent)
    await db.flush()


async def _seed_recommendation(db: AsyncSession, user_id: str):
    import uuid as uuid_mod
    defn = CheatCodeDefinition(
        code="CC-ROUTER",
        title="Router Test Code",
        description="Test code for router",
        category=CheatCodeCategory.save_money,
        difficulty=CheatCodeDifficulty.quick_win,
        estimated_minutes=10,
        steps=[{"step_number": 1, "title": "S1", "description": "Do", "estimated_minutes": 5}],
        potential_savings_min=Decimal("10.00"),
        potential_savings_max=Decimal("50.00"),
    )
    db.add(defn)
    await db.flush()

    rec = Recommendation(
        user_id=uuid_mod.UUID(user_id),
        cheat_code_id=defn.id,
        rank=1,
        explanation="Test explanation",
        explanation_template="general",
        explanation_inputs={},
        confidence="high",
        is_quick_win=True,
    )
    db.add(rec)
    await db.flush()
    return defn, rec


# --- Plan endpoint ---

@pytest.mark.asyncio
async def test_plan_mode(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "plan"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "plan"
    assert "response" in data
    assert "steps" in data
    assert "template_used" in data


@pytest.mark.asyncio
async def test_plan_with_recommendations(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)
    await _seed_recommendation(db_session, user_id)

    resp = await client.post(
        "/coach",
        json={"mode": "plan"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) >= 1
    assert any(s["action"] == "start_recommendation" for s in data["steps"])


# --- Review endpoint ---

@pytest.mark.asyncio
async def test_review_mode(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "review"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "review"
    assert "wins" in data
    assert "response" in data


@pytest.mark.asyncio
async def test_review_no_wins(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "review"},
        headers=headers,
    )
    data = resp.json()
    assert data["template_used"] == "no_wins"
    assert data["wins"] == []


# --- Recap endpoint ---

@pytest.mark.asyncio
async def test_recap_mode(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "recap"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "recap"
    assert "Weekly Recap" in data["response"]
    assert "template_used" in data


# --- Validation ---

@pytest.mark.asyncio
async def test_invalid_mode(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "chat"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Mode must be one of" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_explain_requires_context(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "explain"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "context_type is required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_explain_requires_context_id(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={"mode": "explain", "context_type": "recommendation"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "context_id is required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_plan_does_not_require_context(client: AsyncClient, db_session: AsyncSession):
    """Plan, review, recap don't need context_type/context_id."""
    headers, _ = await _register_and_login(client)

    for mode in ("plan", "review", "recap"):
        resp = await client.post(
            "/coach",
            json={"mode": mode},
            headers=headers,
        )
        assert resp.status_code == 200, f"mode={mode} failed"


@pytest.mark.asyncio
async def test_unauthenticated_coach(client: AsyncClient, db_session: AsyncSession):
    resp = await client.post(
        "/coach",
        json={"mode": "plan"},
    )
    assert resp.status_code == 401


# --- Memory endpoints ---

@pytest.mark.asyncio
async def test_get_memory_no_consent(client: AsyncClient, db_session: AsyncSession):
    """GET /coach/memory returns null without ai_memory consent."""
    headers, _ = await _register_and_login(client)

    resp = await client.get("/coach/memory", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_put_memory_no_consent(client: AsyncClient, db_session: AsyncSession):
    """PUT /coach/memory returns 403 without ai_memory consent."""
    headers, _ = await _register_and_login(client)

    resp = await client.put(
        "/coach/memory",
        json={"tone": "direct"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "ai_memory consent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_put_memory_with_consent(client: AsyncClient, db_session: AsyncSession):
    """PUT /coach/memory creates memory with ai_memory consent."""
    headers, user_id = await _register_and_login(client)
    await _grant_consent(db_session, user_id, ConsentType.ai_memory)

    resp = await client.put(
        "/coach/memory",
        json={"tone": "encouraging", "aggressiveness": "aggressive"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tone"] == "encouraging"
    assert data["aggressiveness"] == "aggressive"


@pytest.mark.asyncio
async def test_get_memory_with_consent(client: AsyncClient, db_session: AsyncSession):
    """GET /coach/memory returns stored preferences after set."""
    headers, user_id = await _register_and_login(client)
    await _grant_consent(db_session, user_id, ConsentType.ai_memory)

    await client.put(
        "/coach/memory",
        json={"tone": "direct"},
        headers=headers,
    )

    resp = await client.get("/coach/memory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tone"] == "direct"
    assert data["aggressiveness"] == "moderate"  # default


@pytest.mark.asyncio
async def test_put_memory_invalid_tone(client: AsyncClient, db_session: AsyncSession):
    """PUT /coach/memory rejects invalid tone value."""
    headers, user_id = await _register_and_login(client)
    await _grant_consent(db_session, user_id, ConsentType.ai_memory)

    resp = await client.put(
        "/coach/memory",
        json={"tone": "sarcastic"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "tone must be one of" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_put_memory_invalid_aggressiveness(client: AsyncClient, db_session: AsyncSession):
    """PUT /coach/memory rejects invalid aggressiveness value."""
    headers, user_id = await _register_and_login(client)
    await _grant_consent(db_session, user_id, ConsentType.ai_memory)

    resp = await client.put(
        "/coach/memory",
        json={"aggressiveness": "extreme"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "aggressiveness must be one of" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_memory(client: AsyncClient, db_session: AsyncSession):
    """DELETE /coach/memory removes preferences."""
    headers, user_id = await _register_and_login(client)
    await _grant_consent(db_session, user_id, ConsentType.ai_memory)

    await client.put(
        "/coach/memory",
        json={"tone": "direct"},
        headers=headers,
    )

    resp = await client.delete("/coach/memory", headers=headers)
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get("/coach/memory", headers=headers)
    assert resp.json() is None


@pytest.mark.asyncio
async def test_delete_memory_unauthenticated(client: AsyncClient, db_session: AsyncSession):
    resp = await client.delete("/coach/memory")
    assert resp.status_code == 401
