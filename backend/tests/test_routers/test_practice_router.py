"""Phase 7 router tests: /practice endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scenario_seed import seed_scenarios


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "practicerouter@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "practicerouter@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}


@pytest.mark.asyncio
async def test_list_scenarios(client: AsyncClient, db_session: AsyncSession):
    """GET /practice/scenarios returns seeded scenarios."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) == 10


@pytest.mark.asyncio
async def test_list_scenarios_filter_category(client: AsyncClient, db_session: AsyncSession):
    """GET /practice/scenarios?category=pay_off_debt filters."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios?category=pay_off_debt", headers=headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) == 2
    assert all(s["category"] == "pay_off_debt" for s in scenarios)


@pytest.mark.asyncio
async def test_get_scenario_by_id(client: AsyncClient, db_session: AsyncSession):
    """GET /practice/scenarios/{id} returns scenario details."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    resp = await client.get(f"/practice/scenarios/{scenario_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == scenario_id
    assert "sliders" in resp.json()
    assert "initial_state" in resp.json()


@pytest.mark.asyncio
async def test_start_scenario(client: AsyncClient, db_session: AsyncSession):
    """POST /practice/start creates a run."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    resp = await client.post(
        "/practice/start",
        json={"scenario_id": scenario_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["confidence"] == "medium"
    assert data["plan_generated"] is False


@pytest.mark.asyncio
async def test_simulate(client: AsyncClient, db_session: AsyncSession):
    """POST /practice/simulate computes outcome."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    # Get S-001 (Savings Rate Simulator)
    resp = await client.get("/practice/scenarios", headers=headers)
    s001 = [s for s in resp.json() if s["code"] == "S-001"][0]

    # Start
    resp = await client.post(
        "/practice/start",
        json={"scenario_id": s001["id"]},
        headers=headers,
    )
    run_id = resp.json()["id"]

    # Simulate
    resp = await client.post(
        "/practice/simulate",
        json={
            "run_id": run_id,
            "slider_values": {"monthly_savings": 400, "expense_reduction": 100},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["computed_outcome"] is not None
    assert data["computed_outcome"]["total_monthly"] == 500
    assert data["confidence"] == "medium"


@pytest.mark.asyncio
async def test_complete_scenario(client: AsyncClient, db_session: AsyncSession):
    """POST /practice/complete generates AAR."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    # Start + simulate + complete
    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    run_id = resp.json()["id"]

    await client.post(
        "/practice/simulate",
        json={"run_id": run_id, "slider_values": {"monthly_savings": 200, "expense_reduction": 50}},
        headers=headers,
    )

    resp = await client.post(
        "/practice/complete", json={"run_id": run_id}, headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["after_action_review"] is not None
    assert "summary" in data["after_action_review"]


@pytest.mark.asyncio
async def test_turn_into_plan(client: AsyncClient, db_session: AsyncSession):
    """POST /practice/turn-into-plan returns plan with caveats."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    # Full flow: start → simulate → complete → turn into plan
    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    run_id = resp.json()["id"]

    await client.post(
        "/practice/simulate",
        json={"run_id": run_id, "slider_values": {"monthly_savings": 300, "expense_reduction": 0}},
        headers=headers,
    )

    await client.post(
        "/practice/complete", json={"run_id": run_id}, headers=headers,
    )

    resp = await client.post(
        "/practice/turn-into-plan", json={"run_id": run_id}, headers=headers,
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["source"] == "practice"
    assert plan["confidence"] == "medium"
    assert len(plan["steps"]) == 3
    assert len(plan["caveats"]) == 3
    assert any("Top 3" in c for c in plan["caveats"])


@pytest.mark.asyncio
async def test_turn_into_plan_before_complete(client: AsyncClient, db_session: AsyncSession):
    """POST /practice/turn-into-plan before completion returns 400."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    run_id = resp.json()["id"]

    resp = await client.post(
        "/practice/turn-into-plan", json={"run_id": run_id}, headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_runs(client: AsyncClient, db_session: AsyncSession):
    """GET /practice/runs lists user's runs."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )

    resp = await client.get("/practice/runs", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_run_by_id(client: AsyncClient, db_session: AsyncSession):
    """GET /practice/runs/{id} returns specific run."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    run_id = resp.json()["id"]

    resp = await client.get(f"/practice/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    """Practice endpoints require authentication."""
    resp = await client.get("/practice/scenarios")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_simulate_completed_rejected(client: AsyncClient, db_session: AsyncSession):
    """POST /practice/simulate on completed run returns 400."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    run_id = resp.json()["id"]

    await client.post(
        "/practice/simulate",
        json={"run_id": run_id, "slider_values": {"monthly_savings": 200, "expense_reduction": 0}},
        headers=headers,
    )
    await client.post(
        "/practice/complete", json={"run_id": run_id}, headers=headers,
    )

    resp = await client.post(
        "/practice/simulate",
        json={"run_id": run_id, "slider_values": {"monthly_savings": 300, "expense_reduction": 50}},
        headers=headers,
    )
    assert resp.status_code == 400
