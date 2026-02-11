"""Enhanced lifecycle tests: pause, resume, abandon, archive validation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import RunStatus
from app.models.user import User
from app.services import cheat_code_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="lifecycle@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _setup_run(db: AsyncSession, user: User):
    """Seed, compute top 3, start a run, return (run, recs)."""
    await seed_cheat_codes(db)
    recs = await ranking_service.compute_top_3(db, user.id)
    run = await cheat_code_service.start_run(
        db, user_id=user.id, recommendation_id=recs[0].id
    )
    return run, recs


@pytest.mark.asyncio
async def test_pause_in_progress_run(db_session: AsyncSession):
    """Can pause an in-progress run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)
    assert run.status == RunStatus.in_progress

    paused = await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert paused.status == RunStatus.paused


@pytest.mark.asyncio
async def test_resume_paused_run(db_session: AsyncSession):
    """Can resume a paused run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )

    resumed = await cheat_code_service.resume_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert resumed.status == RunStatus.in_progress


@pytest.mark.asyncio
async def test_cannot_pause_non_in_progress(db_session: AsyncSession):
    """Cannot pause a run that's not in_progress."""
    from sqlalchemy.exc import NoResultFound

    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    # Pause first
    await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )

    # Try to pause again (now it's paused, not in_progress)
    with pytest.raises(NoResultFound):
        await cheat_code_service.pause_run(
            db_session, run_id=run.id, user_id=user.id
        )


@pytest.mark.asyncio
async def test_cannot_resume_non_paused(db_session: AsyncSession):
    """Cannot resume a run that's not paused."""
    from sqlalchemy.exc import NoResultFound

    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    # Run is in_progress, not paused
    with pytest.raises(NoResultFound):
        await cheat_code_service.resume_run(
            db_session, run_id=run.id, user_id=user.id
        )


@pytest.mark.asyncio
async def test_abandon_in_progress_run(db_session: AsyncSession):
    """Can abandon an in-progress run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    abandoned = await cheat_code_service.abandon_run(
        db_session, run_id=run.id, user_id=user.id, reason="Changed my mind"
    )
    assert abandoned.status == RunStatus.abandoned


@pytest.mark.asyncio
async def test_abandon_paused_run(db_session: AsyncSession):
    """Can abandon a paused run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )

    abandoned = await cheat_code_service.abandon_run(
        db_session, run_id=run.id, user_id=user.id
    )
    assert abandoned.status == RunStatus.abandoned


@pytest.mark.asyncio
async def test_cannot_abandon_completed(db_session: AsyncSession):
    """Cannot abandon a completed run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    # Complete all steps
    for i in range(1, run.total_steps + 1):
        await cheat_code_service.complete_step(
            db_session, run_id=run.id, user_id=user.id, step_number=i
        )

    with pytest.raises(ValueError, match="Cannot abandon run"):
        await cheat_code_service.abandon_run(
            db_session, run_id=run.id, user_id=user.id
        )


@pytest.mark.asyncio
async def test_cannot_abandon_archived(db_session: AsyncSession):
    """Cannot abandon an archived run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    # Complete all steps then archive
    for i in range(1, run.total_steps + 1):
        await cheat_code_service.complete_step(
            db_session, run_id=run.id, user_id=user.id, step_number=i
        )
    await cheat_code_service.archive_run(
        db_session, run_id=run.id, user_id=user.id
    )

    with pytest.raises(ValueError, match="Cannot abandon run"):
        await cheat_code_service.abandon_run(
            db_session, run_id=run.id, user_id=user.id
        )


@pytest.mark.asyncio
async def test_cannot_archive_in_progress(db_session: AsyncSession):
    """Cannot archive a run that's not completed."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    with pytest.raises(ValueError, match="must be 'completed'"):
        await cheat_code_service.archive_run(
            db_session, run_id=run.id, user_id=user.id
        )


@pytest.mark.asyncio
async def test_cannot_archive_abandoned(db_session: AsyncSession):
    """Cannot archive an abandoned run."""
    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    await cheat_code_service.abandon_run(
        db_session, run_id=run.id, user_id=user.id
    )

    with pytest.raises(ValueError, match="must be 'completed'"):
        await cheat_code_service.archive_run(
            db_session, run_id=run.id, user_id=user.id
        )


@pytest.mark.asyncio
async def test_list_runs_by_status(db_session: AsyncSession):
    """Can filter runs by status."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)
    recs = await ranking_service.compute_top_3(db_session, user.id)

    # Start 2 runs (using different recommendations)
    run1 = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs[0].id
    )
    run2 = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs[1].id
    )

    # Pause one
    await cheat_code_service.pause_run(
        db_session, run_id=run1.id, user_id=user.id
    )

    # Filter by in_progress
    in_progress = await cheat_code_service.get_user_runs(
        db_session, user.id, status=RunStatus.in_progress
    )
    assert len(in_progress) == 1
    assert in_progress[0].id == run2.id

    # Filter by paused
    paused = await cheat_code_service.get_user_runs(
        db_session, user.id, status=RunStatus.paused
    )
    assert len(paused) == 1
    assert paused[0].id == run1.id


@pytest.mark.asyncio
async def test_pause_audit_logged(db_session: AsyncSession):
    """Pause events must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "cheatcode.run_paused",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_resume_audit_logged(db_session: AsyncSession):
    """Resume events must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )
    await cheat_code_service.resume_run(
        db_session, run_id=run.id, user_id=user.id
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "cheatcode.run_resumed",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_abandon_audit_logged(db_session: AsyncSession):
    """Abandon events must be audit-logged with reason."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    run, _ = await _setup_run(db_session, user)

    await cheat_code_service.abandon_run(
        db_session, run_id=run.id, user_id=user.id, reason="Too hard"
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "cheatcode.run_abandoned",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].detail["reason"] == "Too hard"
