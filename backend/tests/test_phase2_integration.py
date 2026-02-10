"""Phase 2 end-to-end integration test.

Full lifecycle: register → consent → link account → add transactions →
set goals → get Top 3 → start cheat code → complete step (First Win) →
advance through onboarding → verify audit trail.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLogEvent
from app.services import category_service


@pytest.mark.asyncio
async def test_full_phase2_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """End-to-end Phase 2 lifecycle test."""

    # Seed system categories (required for transaction auto-categorization)
    await category_service.seed_system_categories(db_session)
    await db_session.commit()

    # ──────────────────────────────────────────────────────────
    # Step 1: Register + Login
    # ──────────────────────────────────────────────────────────
    await client.post(
        "/auth/register",
        json={"email": "p2-e2e@example.com", "password": "SecurePass123!"},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "p2-e2e@example.com", "password": "SecurePass123!"},
    )
    token = login_resp.json()["token"]
    user_id = login_resp.json()["user_id"]
    headers = {"X-Session-Token": token}

    # ──────────────────────────────────────────────────────────
    # Step 2: Check initial onboarding state
    # ──────────────────────────────────────────────────────────
    resp = await client.get("/onboarding/state", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "consent"

    # ──────────────────────────────────────────────────────────
    # Step 3: Advance through consent gate
    # ──────────────────────────────────────────────────────────
    resp = await client.post("/onboarding/advance?step=consent", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "account_link"

    # ──────────────────────────────────────────────────────────
    # Step 4: Create account + advance account_link gate
    # ──────────────────────────────────────────────────────────
    resp = await client.post(
        "/accounts/manual",
        json={
            "account_type": "checking",
            "institution_name": "Chase",
            "account_name": "Primary Checking",
            "current_balance": "5000.00",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    account_id = resp.json()["id"]

    resp = await client.post("/onboarding/advance?step=account_link", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "goals"

    # ──────────────────────────────────────────────────────────
    # Step 5: Add transactions (for pattern detection & ranking context)
    # ──────────────────────────────────────────────────────────
    base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    # Netflix recurring - 6 months
    for i in range(6):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"NETFLIX #{1000 + i}",
                "amount": "15.99",
                "transaction_type": "debit",
                "transaction_date": (base_date + timedelta(days=30 * i)).isoformat(),
            },
            headers=headers,
        )

    # Starbucks - 12 weekly
    for i in range(12):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "raw_description": f"STARBUCKS #{2000 + i}",
                "amount": f"{5 + (i % 3)}.50",
                "transaction_type": "debit",
                "transaction_date": (base_date + timedelta(days=7 * i)).isoformat(),
            },
            headers=headers,
        )

    # Detect recurring patterns
    resp = await client.post("/recurring/detect", headers=headers)
    assert resp.status_code == 200

    # ──────────────────────────────────────────────────────────
    # Step 6: Set goals + advance goals gate
    # ──────────────────────────────────────────────────────────
    resp = await client.post(
        "/goals",
        json={
            "goal_type": "save_money",
            "title": "Save for emergency fund",
            "target_amount": "1000.00",
            "priority": "high",
        },
        headers=headers,
    )
    assert resp.status_code == 201

    resp = await client.post(
        "/goals/constraints",
        json={
            "constraint_type": "monthly_income",
            "label": "Salary",
            "amount": "3000.00",
        },
        headers=headers,
    )
    assert resp.status_code == 201

    resp = await client.post("/onboarding/advance?step=goals", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "top_3"

    # ──────────────────────────────────────────────────────────
    # Step 7: Get Top 3 Moves + advance top_3 gate
    # ──────────────────────────────────────────────────────────
    resp = await client.post("/cheat-codes/top-3", headers=headers)
    assert resp.status_code == 200
    top_3 = resp.json()
    assert len(top_3) == 3

    # PRD validations on Top 3
    for rec in top_3:
        assert rec["confidence"] != "low"  # No low confidence
        assert len(rec["explanation"]) > 0  # All explainable
    quick_wins = [r for r in top_3 if r["is_quick_win"]]
    assert len(quick_wins) >= 1  # At least one quick win

    resp = await client.post("/onboarding/advance?step=top_3", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "first_win"

    # ──────────────────────────────────────────────────────────
    # Step 8: First Win — cannot complete without cheat code step
    # ──────────────────────────────────────────────────────────
    resp = await client.post("/onboarding/advance?step=first_win", headers=headers)
    assert resp.status_code == 400  # Must complete a cheat code step first

    # ──────────────────────────────────────────────────────────
    # Step 9: Start cheat code run + complete 1 step
    # ──────────────────────────────────────────────────────────
    # Use the first quick win recommendation
    quick_win_rec = quick_wins[0]
    resp = await client.post(
        "/cheat-codes/runs",
        json={"recommendation_id": quick_win_rec["id"]},
        headers=headers,
    )
    assert resp.status_code == 201
    run_data = resp.json()
    run_id = run_data["id"]
    assert run_data["status"] == "in_progress"

    # Complete step 1
    resp = await client.post(
        f"/cheat-codes/runs/{run_id}/steps/complete",
        json={"step_number": 1, "notes": "Reviewed my recurring charges"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["step"]["status"] == "completed"
    assert resp.json()["run"]["completed_steps"] == 1

    # ──────────────────────────────────────────────────────────
    # Step 10: Coach — explain the recommendation
    # ──────────────────────────────────────────────────────────
    resp = await client.post(
        "/coach",
        json={
            "mode": "explain",
            "context_type": "recommendation",
            "context_id": quick_win_rec["id"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    coach_data = resp.json()
    assert coach_data["mode"] == "explain"
    assert len(coach_data["response"]) > 0
    assert coach_data["template_used"] != ""

    # ──────────────────────────────────────────────────────────
    # Step 11: Now complete first_win (should succeed)
    # ──────────────────────────────────────────────────────────
    resp = await client.post("/onboarding/advance?step=first_win", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["current_step"] == "completed"
    assert resp.json()["completed"] is True

    # Verify onboarding state
    resp = await client.get("/onboarding/state", headers=headers)
    state = resp.json()
    assert state["current_step"] == "completed"
    assert state["consent_completed_at"] is not None
    assert state["account_completed_at"] is not None
    assert state["goals_completed_at"] is not None
    assert state["top_3_completed_at"] is not None
    assert state["first_win_completed_at"] is not None

    # ──────────────────────────────────────────────────────────
    # Step 12: Verify audit trail covers all Phase 2 actions
    # ──────────────────────────────────────────────────────────
    import uuid as uuid_mod

    uid = uuid_mod.UUID(user_id)
    result = await db_session.execute(
        select(AuditLogEvent)
        .where(AuditLogEvent.user_id == uid)
        .order_by(AuditLogEvent.timestamp.asc())
    )
    events = result.scalars().all()
    event_types = {e.event_type for e in events}

    # Phase 0 events
    assert "auth.register" in event_types
    assert "auth.login" in event_types

    # Phase 1 events
    assert "account.created" in event_types
    assert "transaction.created" in event_types
    assert "recurring.detected" in event_types

    # Phase 2 events
    assert "goal.created" in event_types
    assert "constraint.created" in event_types
    assert "ranking.computed" in event_types
    assert "cheatcode.run_started" in event_types
    assert "cheatcode.step_completed" in event_types
    assert "onboarding.step_completed" in event_types
    assert "coach.explain" in event_types
