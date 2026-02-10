"""Coach service tests: Explain + Execute modes only."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import coach_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="coach@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_explain_recommendation(db_session: AsyncSession):
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)
    recs = await ranking_service.compute_top_3(db_session, user.id)

    result = await coach_service.explain(
        db_session,
        user_id=user.id,
        context_type="recommendation",
        context_id=recs[0].id,
    )

    assert result["mode"] == "explain"
    assert result["template_used"] == "recommendation"
    assert len(result["response"]) > 0
    assert isinstance(result["inputs"], dict)
    assert isinstance(result["caveats"], list)


@pytest.mark.asyncio
async def test_explain_cheat_code(db_session: AsyncSession):
    user = await _create_user(db_session)
    definitions = await seed_cheat_codes(db_session)

    result = await coach_service.explain(
        db_session,
        user_id=user.id,
        context_type="cheat_code",
        context_id=definitions[0].id,
    )

    assert result["mode"] == "explain"
    assert result["template_used"] == "cheat_code"
    assert definitions[0].title in result["response"]


@pytest.mark.asyncio
async def test_explain_unknown_context_type(db_session: AsyncSession):
    import uuid
    user = await _create_user(db_session)

    result = await coach_service.explain(
        db_session,
        user_id=user.id,
        context_type="unknown_type",
        context_id=uuid.uuid4(),
    )

    assert result["mode"] == "explain"
    assert "not available" in result["response"] or "not supported" in result["response"]


@pytest.mark.asyncio
async def test_execute_start_run(db_session: AsyncSession):
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)
    recs = await ranking_service.compute_top_3(db_session, user.id)

    result = await coach_service.execute(
        db_session,
        user_id=user.id,
        context_type="recommendation",
        context_id=recs[0].id,
    )

    assert result["mode"] == "execute"
    assert "run_id" in result["inputs"]
    assert "Started" in result["response"]


@pytest.mark.asyncio
async def test_coach_interactions_audit_logged(db_session: AsyncSession):
    """Coach interactions must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)
    recs = await ranking_service.compute_top_3(db_session, user.id)

    await coach_service.explain(
        db_session,
        user_id=user.id,
        context_type="recommendation",
        context_id=recs[0].id,
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "coach.explain",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
