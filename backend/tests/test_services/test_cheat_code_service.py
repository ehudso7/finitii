"""Cheat code service tests: start run, complete step, lifecycle."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import RunStatus
from app.models.user import User
from app.services import cheat_code_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="cc@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _setup_recommendation(db: AsyncSession, user: User):
    """Seed codes, compute top 3, return first recommendation."""
    await seed_cheat_codes(db)
    recs = await ranking_service.compute_top_3(db, user.id)
    return recs[0]


@pytest.mark.asyncio
async def test_start_run(db_session: AsyncSession):
    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )
    assert run.status == RunStatus.in_progress
    assert run.total_steps > 0
    assert run.completed_steps == 0
    assert run.started_at is not None


@pytest.mark.asyncio
async def test_start_run_creates_steps(db_session: AsyncSession):
    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )
    steps = await cheat_code_service.get_run_steps(db_session, run.id)
    assert len(steps) == run.total_steps
    assert all(s.status == RunStatus.not_started for s in steps)


@pytest.mark.asyncio
async def test_complete_step(db_session: AsyncSession):
    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )

    step = await cheat_code_service.complete_step(
        db_session,
        run_id=run.id,
        user_id=user.id,
        step_number=1,
        notes="Done!",
    )
    assert step.status == RunStatus.completed
    assert step.completed_at is not None
    assert step.notes == "Done!"

    # Run should show 1 completed step
    updated_run = await cheat_code_service.get_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert updated_run.completed_steps == 1


@pytest.mark.asyncio
async def test_complete_all_steps_completes_run(db_session: AsyncSession):
    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )

    # Complete all steps
    for i in range(1, run.total_steps + 1):
        await cheat_code_service.complete_step(
            db_session, run_id=run.id, user_id=user.id, step_number=i
        )

    updated_run = await cheat_code_service.get_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert updated_run.status == RunStatus.completed
    assert updated_run.completed_at is not None
    assert updated_run.completed_steps == updated_run.total_steps


@pytest.mark.asyncio
async def test_archive_run(db_session: AsyncSession):
    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )

    archived = await cheat_code_service.archive_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert archived.status == RunStatus.archived


@pytest.mark.asyncio
async def test_get_user_runs(db_session: AsyncSession):
    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )

    runs = await cheat_code_service.get_user_runs(db_session, user.id)
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_step_completion_audit_logged(db_session: AsyncSession):
    """Step completions must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    rec = await _setup_recommendation(db_session, user)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=rec.id
    )
    await cheat_code_service.complete_step(
        db_session, run_id=run.id, user_id=user.id, step_number=1
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "cheatcode.step_completed",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].detail["step_number"] == 1
