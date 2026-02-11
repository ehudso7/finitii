"""Phase 2 router tests: onboarding, goals, cheat codes, coach."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import category_service


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    """Register a user, login, return (headers, user_id)."""
    await client.post(
        "/auth/register",
        json={"email": "p2router@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p2router@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


@pytest.mark.asyncio
async def test_onboarding_state(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)

    resp = await client.get("/onboarding/state", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "consent"


@pytest.mark.asyncio
async def test_onboarding_advance(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)

    resp = await client.post("/onboarding/advance?step=consent", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "account_link"


@pytest.mark.asyncio
async def test_onboarding_cannot_skip(client: AsyncClient, db_session: AsyncSession):
    headers, user_id = await _register_and_login(client)

    resp = await client.post("/onboarding/advance?step=goals", headers=headers)
    assert resp.status_code == 400
    assert "Cannot complete step" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_goal(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/goals",
        json={
            "goal_type": "save_money",
            "title": "Save for vacation",
            "target_amount": "2000.00",
            "priority": "high",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Save for vacation"
    assert data["goal_type"] == "save_money"


@pytest.mark.asyncio
async def test_list_goals(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    await client.post(
        "/goals",
        json={"goal_type": "save_money", "title": "Goal 1"},
        headers=headers,
    )
    await client.post(
        "/goals",
        json={"goal_type": "reduce_spending", "title": "Goal 2"},
        headers=headers,
    )

    resp = await client.get("/goals", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_deactivate_goal(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/goals",
        json={"goal_type": "save_money", "title": "Deactivate me"},
        headers=headers,
    )
    goal_id = resp.json()["id"]

    resp = await client.delete(f"/goals/{goal_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"


@pytest.mark.asyncio
async def test_create_constraint(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/goals/constraints",
        json={
            "constraint_type": "monthly_income",
            "label": "Salary",
            "amount": "5000.00",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["label"] == "Salary"


@pytest.mark.asyncio
async def test_list_constraints(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    await client.post(
        "/goals/constraints",
        json={"constraint_type": "monthly_income", "label": "Salary", "amount": "5000.00"},
        headers=headers,
    )

    resp = await client.get("/goals/constraints", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_seed_cheat_codes(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post("/cheat-codes/seed", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["seeded"] == 25


@pytest.mark.asyncio
async def test_compute_top_3(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post("/cheat-codes/top-3", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3

    # PRD: all have explanations
    for rec in data:
        assert "explanation" in rec
        assert len(rec["explanation"]) > 0
        assert "confidence" in rec
        assert rec["confidence"] != "low"  # PRD: no low confidence

    # PRD: at least one quick win
    quick_wins = [r for r in data if r["is_quick_win"]]
    assert len(quick_wins) >= 1


@pytest.mark.asyncio
async def test_get_recommendations(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    # First compute
    await client.post("/cheat-codes/top-3", headers=headers)

    # Then get
    resp = await client.get("/cheat-codes/recommendations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_start_run(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    # Compute top 3
    top3_resp = await client.post("/cheat-codes/top-3", headers=headers)
    rec_id = top3_resp.json()[0]["id"]

    # Start run
    resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": rec_id},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["total_steps"] > 0
    assert data["completed_steps"] == 0
    assert len(data["steps"]) > 0


@pytest.mark.asyncio
async def test_complete_step(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    top3_resp = await client.post("/cheat-codes/top-3", headers=headers)
    rec_id = top3_resp.json()[0]["id"]

    run_resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": rec_id},
        headers=headers,
    )
    run_id = run_resp.json()["id"]

    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/steps/complete",
        json={"step_number": 1, "notes": "Reviewed my subscriptions"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["step"]["status"] == "completed"
    assert data["run"]["completed_steps"] == 1


@pytest.mark.asyncio
async def test_get_run(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    top3_resp = await client.post("/cheat-codes/top-3", headers=headers)
    rec_id = top3_resp.json()[0]["id"]

    run_resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": rec_id},
        headers=headers,
    )
    run_id = run_resp.json()["id"]

    resp = await client.get(f"/cheat-codes/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id


@pytest.mark.asyncio
async def test_coach_explain(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    # Setup: get a recommendation to explain
    top3_resp = await client.post("/cheat-codes/top-3", headers=headers)
    rec_id = top3_resp.json()[0]["id"]

    resp = await client.post(
        "/coach",
        json={
            "mode": "explain",
            "context_type": "recommendation",
            "context_id": rec_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "explain"
    assert len(data["response"]) > 0
    assert data["template_used"] == "recommendation"


@pytest.mark.asyncio
async def test_coach_execute(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    top3_resp = await client.post("/cheat-codes/top-3", headers=headers)
    rec_id = top3_resp.json()[0]["id"]

    resp = await client.post(
        "/coach",
        json={
            "mode": "execute",
            "context_type": "recommendation",
            "context_id": rec_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "execute"
    assert "run_id" in data["inputs"]


@pytest.mark.asyncio
async def test_coach_invalid_mode(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post(
        "/coach",
        json={
            "mode": "chat",  # Not allowed in Phase 2
            "context_type": "recommendation",
            "context_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=headers,
    )
    assert resp.status_code == 400
