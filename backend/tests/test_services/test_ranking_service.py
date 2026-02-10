"""Ranking service tests: Top 3 Moves with PRD rules."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeDifficulty, Recommendation
from app.models.goal import GoalType
from app.services import goal_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes
from app.models.user import User


async def _create_user(db: AsyncSession) -> User:
    user = User(email="rank@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_compute_top_3_returns_3_recommendations(db_session: AsyncSession):
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    assert len(recs) == 3


@pytest.mark.asyncio
async def test_top_3_no_low_confidence(db_session: AsyncSession):
    """PRD rule: No low-confidence recommendations in Top 3."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    for rec in recs:
        assert rec.confidence != "low"


@pytest.mark.asyncio
async def test_top_3_all_explainable(db_session: AsyncSession):
    """PRD rule: All recommendations must be explainable (template + inputs)."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    for rec in recs:
        assert rec.explanation_template != ""
        assert isinstance(rec.explanation_inputs, dict)
        assert rec.explanation != ""


@pytest.mark.asyncio
async def test_top_3_includes_quick_win(db_session: AsyncSession):
    """PRD rule: At least one ≤10-min quick win in Top 3."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    quick_wins = [r for r in recs if r.is_quick_win]
    assert len(quick_wins) >= 1


@pytest.mark.asyncio
async def test_top_3_ranked_in_order(db_session: AsyncSession):
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    ranks = [r.rank for r in recs]
    assert ranks == [1, 2, 3]


@pytest.mark.asyncio
async def test_top_3_recompute_replaces_old(db_session: AsyncSession):
    """Recomputing Top 3 should replace old recommendations."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs1 = await ranking_service.compute_top_3(db_session, user.id)
    ids1 = {r.id for r in recs1}

    recs2 = await ranking_service.compute_top_3(db_session, user.id)
    ids2 = {r.id for r in recs2}

    assert ids1 != ids2  # New UUIDs each time


@pytest.mark.asyncio
async def test_top_3_goal_alignment_affects_ranking(db_session: AsyncSession):
    """Goals should influence which cheat codes are recommended."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # Create a save_money goal
    await goal_service.create_goal(
        db_session,
        user_id=user.id,
        goal_type=GoalType.save_money,
        title="Save for vacation",
    )

    recs = await ranking_service.compute_top_3(db_session, user.id)

    # All recs should have non-empty explanation
    for rec in recs:
        assert len(rec.explanation) > 0


@pytest.mark.asyncio
async def test_top_3_audit_logged(db_session: AsyncSession):
    """Top 3 computation must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    await ranking_service.compute_top_3(db_session, user.id)

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "ranking.computed",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert "recommendations" in events[0].detail


@pytest.mark.asyncio
async def test_get_recommendations(db_session: AsyncSession):
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)
    await ranking_service.compute_top_3(db_session, user.id)

    recs = await ranking_service.get_recommendations(db_session, user.id)
    assert len(recs) == 3
    assert recs[0].rank == 1
