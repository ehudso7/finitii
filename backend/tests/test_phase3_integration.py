"""Phase 3 end-to-end integration test.

Full lifecycle: seed → goals → Top 3 → start run → pause → resume →
complete all steps → report outcome → archive → recompute Top 3 (exclusion) →
outcomes summary.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    await client.post(
        "/auth/register",
        json={"email": "p3e2e@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p3e2e@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


@pytest.mark.asyncio
async def test_phase3_full_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """End-to-end: full cheat code lifecycle with outcomes."""
    headers, user_id = await _register_and_login(client)

    # 1. Seed 25 cheat codes
    resp = await client.post("/cheat-codes/seed", headers=headers)
    assert resp.json()["seeded"] == 25

    # 2. Create a goal to influence ranking
    resp = await client.post(
        "/goals",
        json={"goal_type": "save_money", "title": "Build savings"},
        headers=headers,
    )
    assert resp.status_code == 201

    # 3. Compute Top 3
    resp = await client.post("/cheat-codes/top-3", headers=headers)
    assert resp.status_code == 200
    top3 = resp.json()
    assert len(top3) == 3
    assert any(r["is_quick_win"] for r in top3)
    for r in top3:
        assert r["confidence"] != "low"
        assert len(r["explanation"]) > 0

    first_rec_id = top3[0]["id"]
    first_code_id = top3[0]["cheat_code"]["id"]

    # 4. Start a run
    resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": first_rec_id},
        headers=headers,
    )
    assert resp.status_code == 201
    run = resp.json()
    run_id = run["id"]
    total_steps = run["total_steps"]
    assert run["status"] == "in_progress"
    assert total_steps > 0

    # 5. Pause the run
    resp = await client.post(f"/cheat-codes/runs/{run_id}/pause", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    # 6. Verify run appears as paused in list
    resp = await client.get("/cheat-codes/runs?status=paused", headers=headers)
    assert resp.status_code == 200
    assert any(r["id"] == run_id for r in resp.json())

    # 7. Resume the run
    resp = await client.post(f"/cheat-codes/runs/{run_id}/resume", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # 8. Complete all steps
    for i in range(1, total_steps + 1):
        resp = await client.post(
            f"/cheat-codes/runs/{run_id}/steps/complete",
            json={"step_number": i, "notes": f"Step {i} done"},
            headers=headers,
        )
        assert resp.status_code == 200

    # Verify run is completed
    resp = await client.get(f"/cheat-codes/runs/{run_id}", headers=headers)
    assert resp.json()["status"] == "completed"
    assert resp.json()["completed_steps"] == total_steps

    # 9. Report outcome
    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/outcome",
        json={
            "reported_savings": "29.99",
            "reported_savings_period": "monthly",
            "notes": "Cancelled streaming service",
            "user_satisfaction": 5,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    outcome = resp.json()
    assert outcome["outcome_type"] == "user_reported"
    assert outcome["reported_savings"] == "29.99"

    # 10. Get outcome
    resp = await client.get(f"/cheat-codes/runs/{run_id}/outcome", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["reported_savings"] == "29.99"

    # 11. Archive the run
    resp = await client.post(f"/cheat-codes/runs/{run_id}/archive", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"

    # 12. Recompute Top 3 — completed code should be excluded
    resp = await client.post("/cheat-codes/top-3", headers=headers)
    assert resp.status_code == 200
    new_top3 = resp.json()
    assert len(new_top3) == 3
    new_code_ids = {r["cheat_code"]["id"] for r in new_top3}
    assert first_code_id not in new_code_ids

    # 13. Check outcomes summary
    resp = await client.get("/cheat-codes/outcomes/summary", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_outcomes"] == 1
    assert summary["total_reported_savings"] == "29.99"

    # 14. Start another run, abandon it
    second_rec_id = new_top3[0]["id"]
    resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": second_rec_id},
        headers=headers,
    )
    assert resp.status_code == 201
    second_run_id = resp.json()["id"]

    resp = await client.post(
        f"/cheat-codes/runs/{second_run_id}/abandon",
        json={"reason": "Too complex for now"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "abandoned"

    # 15. List all runs — should see both
    resp = await client.get("/cheat-codes/runs", headers=headers)
    assert resp.status_code == 200
    all_runs = resp.json()
    assert len(all_runs) >= 2
    statuses = {r["status"] for r in all_runs}
    assert "archived" in statuses
    assert "abandoned" in statuses
