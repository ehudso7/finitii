"""Phase 3 router tests: lifecycle endpoints, outcomes, enhanced cheat codes."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register_and_login(client: AsyncClient) -> tuple[dict, str]:
    """Register a user, login, return (headers, user_id)."""
    await client.post(
        "/auth/register",
        json={"email": "p3router@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p3router@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}, data["user_id"]


async def _start_run(client: AsyncClient, headers: dict) -> tuple[str, dict]:
    """Compute top 3, start a run, return (run_id, run_data)."""
    top3_resp = await client.post("/cheat-codes/top-3", headers=headers)
    rec_id = top3_resp.json()[0]["id"]

    run_resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": rec_id},
        headers=headers,
    )
    data = run_resp.json()
    return data["id"], data


async def _complete_run(client: AsyncClient, headers: dict, run_id: str, total_steps: int):
    """Complete all steps in a run."""
    for i in range(1, total_steps + 1):
        await client.post(
            f"/cheat-codes/runs/{run_id}/steps/complete",
            json={"step_number": i},
            headers=headers,
        )


# --- List runs ---

@pytest.mark.asyncio
async def test_list_runs(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    resp = await client.get("/cheat-codes/runs", headers=headers)
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1
    assert any(r["id"] == run_id for r in runs)


@pytest.mark.asyncio
async def test_list_runs_filter_by_status(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    # Filter in_progress
    resp = await client.get("/cheat-codes/runs?status=in_progress", headers=headers)
    assert resp.status_code == 200
    runs = resp.json()
    assert all(r["status"] == "in_progress" for r in runs)


@pytest.mark.asyncio
async def test_list_runs_invalid_status(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/cheat-codes/runs?status=invalid", headers=headers)
    assert resp.status_code == 400


# --- Pause ---

@pytest.mark.asyncio
async def test_pause_run(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    resp = await client.post(f"/cheat-codes/runs/{run_id}/pause", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_pause_invalid_run_id(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.post("/cheat-codes/runs/not-a-uuid/pause", headers=headers)
    assert resp.status_code == 400


# --- Resume ---

@pytest.mark.asyncio
async def test_resume_run(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    # Pause first
    await client.post(f"/cheat-codes/runs/{run_id}/pause", headers=headers)

    # Resume
    resp = await client.post(f"/cheat-codes/runs/{run_id}/resume", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


# --- Abandon ---

@pytest.mark.asyncio
async def test_abandon_run(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/abandon",
        json={"reason": "Changed my mind"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "abandoned"


@pytest.mark.asyncio
async def test_abandon_run_no_body(client: AsyncClient, db_session: AsyncSession):
    """Abandon without a body should work (reason is optional)."""
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/abandon",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "abandoned"


@pytest.mark.asyncio
async def test_abandon_completed_fails(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, run_data = await _start_run(client, headers)
    await _complete_run(client, headers, run_id, run_data["total_steps"])

    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/abandon",
        headers=headers,
    )
    assert resp.status_code == 400


# --- Archive ---

@pytest.mark.asyncio
async def test_archive_run(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, run_data = await _start_run(client, headers)
    await _complete_run(client, headers, run_id, run_data["total_steps"])

    resp = await client.post(f"/cheat-codes/runs/{run_id}/archive", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_archive_in_progress_fails(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    resp = await client.post(f"/cheat-codes/runs/{run_id}/archive", headers=headers)
    assert resp.status_code == 400


# --- Outcome: report ---

@pytest.mark.asyncio
async def test_report_outcome(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, run_data = await _start_run(client, headers)
    await _complete_run(client, headers, run_id, run_data["total_steps"])

    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/outcome",
        json={
            "reported_savings": "29.99",
            "reported_savings_period": "monthly",
            "notes": "Cancelled streaming",
            "user_satisfaction": 5,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["outcome_type"] == "user_reported"
    assert data["reported_savings"] == "29.99"
    assert data["verification_status"] == "unverified"
    assert data["user_satisfaction"] == 5


@pytest.mark.asyncio
async def test_report_outcome_in_progress_fails(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, _ = await _start_run(client, headers)

    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/outcome",
        json={"reported_savings": "10.00"},
        headers=headers,
    )
    assert resp.status_code == 400


# --- Outcome: get ---

@pytest.mark.asyncio
async def test_get_outcome(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, run_data = await _start_run(client, headers)
    await _complete_run(client, headers, run_id, run_data["total_steps"])

    # Report
    await client.post(
        f"/cheat-codes/runs/{run_id}/outcome",
        json={"reported_savings": "15.00", "reported_savings_period": "monthly"},
        headers=headers,
    )

    # Get
    resp = await client.get(f"/cheat-codes/runs/{run_id}/outcome", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reported_savings"] == "15.00"
    assert data["run_id"] == run_id


@pytest.mark.asyncio
async def test_get_outcome_not_found(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, run_data = await _start_run(client, headers)
    await _complete_run(client, headers, run_id, run_data["total_steps"])

    resp = await client.get(f"/cheat-codes/runs/{run_id}/outcome", headers=headers)
    assert resp.status_code == 404


# --- Outcome: summary ---

@pytest.mark.asyncio
async def test_outcomes_summary(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)
    run_id, run_data = await _start_run(client, headers)
    await _complete_run(client, headers, run_id, run_data["total_steps"])

    await client.post(
        f"/cheat-codes/runs/{run_id}/outcome",
        json={"reported_savings": "50.00", "reported_savings_period": "one_time"},
        headers=headers,
    )

    resp = await client.get("/cheat-codes/outcomes/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_outcomes"] == 1
    assert data["total_reported_savings"] == "50.00"
    assert len(data["outcomes"]) == 1


@pytest.mark.asyncio
async def test_outcomes_summary_empty(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client)

    resp = await client.get("/cheat-codes/outcomes/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_outcomes"] == 0
    assert data["total_reported_savings"] == "0.00"


# --- Expanded seed (25 codes) ---

@pytest.mark.asyncio
async def test_seed_25_codes(client: AsyncClient, db_session: AsyncSession):
    """Phase 3: library expanded to 25 cheat codes."""
    headers, _ = await _register_and_login(client)

    resp = await client.post("/cheat-codes/seed", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["seeded"] == 25
