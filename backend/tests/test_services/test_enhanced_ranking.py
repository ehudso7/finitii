"""Enhanced ranking tests: exclusion of completed/in-progress codes, outcome boost."""

import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeDefinition, Recommendation, RunStatus
from app.models.user import User
from app.services import cheat_code_service, outcome_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="ranking@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_ranking_excludes_completed_codes(db_session: AsyncSession):
    """Completed codes should not appear in new Top 3 (if enough alternatives)."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # Compute first Top 3
    recs1 = await ranking_service.compute_top_3(db_session, user.id)
    first_code_ids = {r.cheat_code_id for r in recs1}

    # Start and complete a run from the first recommendation
    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs1[0].id
    )
    for i in range(1, run.total_steps + 1):
        await cheat_code_service.complete_step(
            db_session, run_id=run.id, user_id=user.id, step_number=i
        )

    # Recompute Top 3
    recs2 = await ranking_service.compute_top_3(db_session, user.id)
    second_code_ids = {r.cheat_code_id for r in recs2}

    # The completed code should not appear in the new Top 3
    # (we have 25 codes, so there are enough alternatives)
    completed_code_id = run.cheat_code_id
    assert completed_code_id not in second_code_ids


@pytest.mark.asyncio
async def test_ranking_excludes_in_progress_codes(db_session: AsyncSession):
    """In-progress codes should not appear in new Top 3."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)

    # Start a run (in_progress)
    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs[0].id
    )

    # Recompute
    recs2 = await ranking_service.compute_top_3(db_session, user.id)
    new_code_ids = {r.cheat_code_id for r in recs2}

    assert run.cheat_code_id not in new_code_ids


@pytest.mark.asyncio
async def test_ranking_excludes_paused_codes(db_session: AsyncSession):
    """Paused codes should not appear in new Top 3."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)

    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs[0].id
    )
    await cheat_code_service.pause_run(
        db_session, run_id=run.id, user_id=user.id
    )

    recs2 = await ranking_service.compute_top_3(db_session, user.id)
    new_code_ids = {r.cheat_code_id for r in recs2}

    assert run.cheat_code_id not in new_code_ids


@pytest.mark.asyncio
async def test_ranking_still_returns_3(db_session: AsyncSession):
    """Even after exclusions, Top 3 returns 3 items (25 codes available)."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # Complete 3 runs
    for _ in range(3):
        recs = await ranking_service.compute_top_3(db_session, user.id)
        run = await cheat_code_service.start_run(
            db_session, user_id=user.id, recommendation_id=recs[0].id
        )
        for i in range(1, run.total_steps + 1):
            await cheat_code_service.complete_step(
                db_session, run_id=run.id, user_id=user.id, step_number=i
            )

    # Should still get 3 recommendations
    final_recs = await ranking_service.compute_top_3(db_session, user.id)
    assert len(final_recs) == 3


@pytest.mark.asyncio
async def test_ranking_full_recompute_replaces_old(db_session: AsyncSession):
    """Recompute deletes old recommendations and creates new ones."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs1 = await ranking_service.compute_top_3(db_session, user.id)
    old_ids = {r.id for r in recs1}

    recs2 = await ranking_service.compute_top_3(db_session, user.id)
    new_ids = {r.id for r in recs2}

    # Old IDs should not exist anymore
    assert old_ids.isdisjoint(new_ids)


@pytest.mark.asyncio
async def test_ranking_quick_win_guarantee(db_session: AsyncSession):
    """PRD rule: at least 1 quick win in Top 3."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    assert any(r.is_quick_win for r in recs)


@pytest.mark.asyncio
async def test_ranking_no_low_confidence(db_session: AsyncSession):
    """PRD rule: no low-confidence recommendations in Top 3."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    for r in recs:
        assert r.confidence != "low"


@pytest.mark.asyncio
async def test_ranking_all_explainable(db_session: AsyncSession):
    """PRD rule: all recommendations must have explanation with template."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    recs = await ranking_service.compute_top_3(db_session, user.id)
    for r in recs:
        assert len(r.explanation) > 0
        assert r.explanation_template in ranking_service.TEMPLATES
        assert isinstance(r.explanation_inputs, dict)
