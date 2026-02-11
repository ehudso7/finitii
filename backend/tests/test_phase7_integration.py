"""Phase 7 integration test: full learn + practice flow through API."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.lesson_seed import seed_lessons
from app.services.scenario_seed import seed_scenarios


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "p7integ@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p7integ@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}


@pytest.mark.asyncio
async def test_full_learn_flow(client: AsyncClient, db_session: AsyncSession):
    """E2E: list lessons → start → complete all sections → verify completion."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    # List lessons
    resp = await client.get("/learn/lessons", headers=headers)
    assert resp.status_code == 200
    lessons = resp.json()
    assert len(lessons) == 10

    # Pick a lesson with 2 sections (L-002)
    l002 = [l for l in lessons if l["code"] == "L-002"][0]
    lesson_id = l002["id"]
    total = l002["total_sections"]
    assert total == 2

    # Start lesson
    resp = await client.post(
        "/learn/start", json={"lesson_id": lesson_id}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # Complete all sections
    for section_num in range(1, total + 1):
        resp = await client.post(
            "/learn/complete-section",
            json={"lesson_id": lesson_id, "section_number": section_num},
            headers=headers,
        )
        assert resp.status_code == 200

    # Should be auto-completed
    assert resp.json()["status"] == "completed"
    assert resp.json()["completed_sections"] == total

    # Verify in progress list
    resp = await client.get("/learn/progress", headers=headers)
    assert resp.status_code == 200
    progress = resp.json()
    assert len(progress) == 1
    assert progress[0]["status"] == "completed"

    # Restart and verify reset
    resp = await client.post(
        "/learn/start", json={"lesson_id": lesson_id}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    assert resp.json()["completed_sections"] == 0


@pytest.mark.asyncio
async def test_full_practice_flow(client: AsyncClient, db_session: AsyncSession):
    """E2E: list scenarios → start → simulate → complete → AAR → turn into plan."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    # List scenarios
    resp = await client.get("/practice/scenarios", headers=headers)
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) == 10

    # Pick S-001 (Savings Rate Simulator)
    s001 = [s for s in scenarios if s["code"] == "S-001"][0]
    scenario_id = s001["id"]

    # Verify sliders are present
    assert len(s001["sliders"]) == 2
    assert s001["sliders"][0]["key"] == "monthly_savings"

    # Start scenario
    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    assert resp.status_code == 200
    run = resp.json()
    run_id = run["id"]
    assert run["confidence"] == "medium"
    assert run["status"] == "in_progress"

    # Simulate with custom sliders
    resp = await client.post(
        "/practice/simulate",
        json={
            "run_id": run_id,
            "slider_values": {"monthly_savings": 500, "expense_reduction": 200},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    run = resp.json()
    assert run["computed_outcome"]["total_monthly"] == 700
    assert run["computed_outcome"]["total_annual"] == 8400
    assert run["confidence"] == "medium"

    # Simulate again (re-simulation allowed while in progress)
    resp = await client.post(
        "/practice/simulate",
        json={
            "run_id": run_id,
            "slider_values": {"monthly_savings": 300, "expense_reduction": 100},
        },
        headers=headers,
    )
    assert resp.status_code == 200
    run = resp.json()
    assert run["computed_outcome"]["total_monthly"] == 400

    # Complete scenario
    resp = await client.post(
        "/practice/complete", json={"run_id": run_id}, headers=headers,
    )
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "completed"
    assert run["after_action_review"] is not None
    assert "summary" in run["after_action_review"]
    assert "what_worked" in run["after_action_review"]
    assert "improvement" in run["after_action_review"]
    assert "learning_points" in run["after_action_review"]
    assert run["after_action_review"]["confidence"] == "medium"

    # Turn into plan
    resp = await client.post(
        "/practice/turn-into-plan", json={"run_id": run_id}, headers=headers,
    )
    assert resp.status_code == 200
    plan = resp.json()
    assert plan["source"] == "practice"
    assert plan["confidence"] == "medium"
    assert plan["scenario_title"] == "Savings Rate Simulator"
    assert len(plan["steps"]) == 3
    assert plan["steps"][0]["action"] == "apply_learning"
    assert plan["steps"][0]["source"] == "practice"
    assert plan["steps"][1]["action"] == "category_specific"
    assert plan["steps"][2]["action"] == "validate_with_data"
    assert any("Top 3" in c for c in plan["caveats"])
    assert any("simulated" in c.lower() for c in plan["caveats"])

    # Verify run now shows plan_generated
    resp = await client.get(f"/practice/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["plan_generated"] is True

    # Verify runs listing
    resp = await client.get("/practice/runs", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_practice_confidence_cap_enforced(client: AsyncClient, db_session: AsyncSession):
    """Confidence is ALWAYS medium throughout entire practice flow."""
    headers = await _register_and_login(client)
    await seed_scenarios(db_session)

    resp = await client.get("/practice/scenarios", headers=headers)
    scenario_id = resp.json()[0]["id"]

    # Start
    resp = await client.post(
        "/practice/start", json={"scenario_id": scenario_id}, headers=headers,
    )
    assert resp.json()["confidence"] == "medium"
    run_id = resp.json()["id"]

    # Simulate
    resp = await client.post(
        "/practice/simulate",
        json={"run_id": run_id, "slider_values": {"monthly_savings": 800, "expense_reduction": 500}},
        headers=headers,
    )
    assert resp.json()["confidence"] == "medium"

    # Complete
    resp = await client.post(
        "/practice/complete", json={"run_id": run_id}, headers=headers,
    )
    assert resp.json()["confidence"] == "medium"
    assert resp.json()["after_action_review"]["confidence"] == "medium"

    # Plan
    resp = await client.post(
        "/practice/turn-into-plan", json={"run_id": run_id}, headers=headers,
    )
    assert resp.json()["confidence"] == "medium"
