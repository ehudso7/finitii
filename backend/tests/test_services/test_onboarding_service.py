"""Onboarding service tests: gate flow enforcement, First Win hard gate."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onboarding import OnboardingStep
from app.models.user import User
from app.services import cheat_code_service, onboarding_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="onboard@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_get_or_create_state(db_session: AsyncSession):
    user = await _create_user(db_session)
    state = await onboarding_service.get_or_create_state(db_session, user.id)
    assert state.current_step == OnboardingStep.consent
    assert state.consent_completed_at is None


@pytest.mark.asyncio
async def test_get_or_create_idempotent(db_session: AsyncSession):
    user = await _create_user(db_session)
    state1 = await onboarding_service.get_or_create_state(db_session, user.id)
    state2 = await onboarding_service.get_or_create_state(db_session, user.id)
    assert state1.id == state2.id


@pytest.mark.asyncio
async def test_advance_consent_step(db_session: AsyncSession):
    user = await _create_user(db_session)
    state = await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.consent
    )
    assert state.current_step == OnboardingStep.account_link
    assert state.consent_completed_at is not None


@pytest.mark.asyncio
async def test_advance_full_sequence(db_session: AsyncSession):
    """Test advancing through all gates except first_win (needs cheat code)."""
    user = await _create_user(db_session)

    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.consent
    )
    state = await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.account_link
    )
    assert state.current_step == OnboardingStep.goals

    state = await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.goals
    )
    assert state.current_step == OnboardingStep.top_3

    state = await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.top_3
    )
    assert state.current_step == OnboardingStep.first_win


@pytest.mark.asyncio
async def test_cannot_skip_steps(db_session: AsyncSession):
    """Cannot advance a step that is not the current step."""
    user = await _create_user(db_session)

    # Current step is consent, trying to advance goals should fail
    with pytest.raises(ValueError, match="Cannot complete step"):
        await onboarding_service.advance_step(
            db_session, user_id=user.id, completed_step=OnboardingStep.goals
        )


@pytest.mark.asyncio
async def test_first_win_requires_completed_step(db_session: AsyncSession):
    """First Win hard gate: must have completed at least 1 cheat code step."""
    user = await _create_user(db_session)

    # Advance to first_win step
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.consent
    )
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.account_link
    )
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.goals
    )
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.top_3
    )

    # Trying to complete first_win without completing any cheat code step should fail
    with pytest.raises(ValueError, match="must start a cheat code"):
        await onboarding_service.advance_step(
            db_session, user_id=user.id, completed_step=OnboardingStep.first_win
        )


@pytest.mark.asyncio
async def test_first_win_succeeds_after_step_completion(db_session: AsyncSession):
    """First Win passes when user has completed at least 1 cheat code step."""
    user = await _create_user(db_session)

    # Advance to first_win step
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.consent
    )
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.account_link
    )
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.goals
    )
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.top_3
    )

    # Now seed codes, compute top 3, start a run, complete 1 step
    await seed_cheat_codes(db_session)
    recs = await ranking_service.compute_top_3(db_session, user.id)
    run = await cheat_code_service.start_run(
        db_session, user_id=user.id, recommendation_id=recs[0].id
    )
    await cheat_code_service.complete_step(
        db_session, run_id=run.id, user_id=user.id, step_number=1
    )

    # Now first_win should succeed
    state = await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.first_win
    )
    assert state.current_step == OnboardingStep.completed
    assert state.first_win_completed_at is not None
    assert state.first_win_cheat_code_run_id == run.id


@pytest.mark.asyncio
async def test_is_onboarding_complete(db_session: AsyncSession):
    user = await _create_user(db_session)

    # Initially not complete
    assert await onboarding_service.is_onboarding_complete(db_session, user.id) is False


@pytest.mark.asyncio
async def test_advance_step_audit_logged(db_session: AsyncSession):
    """Onboarding step advances must be audit-logged."""
    from sqlalchemy import select
    from app.models.audit import AuditLogEvent

    user = await _create_user(db_session)
    await onboarding_service.advance_step(
        db_session, user_id=user.id, completed_step=OnboardingStep.consent
    )

    result = await db_session.execute(
        select(AuditLogEvent).where(
            AuditLogEvent.user_id == user.id,
            AuditLogEvent.event_type == "onboarding.step_completed",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].detail["completed_step"] == "consent"
    assert events[0].detail["new_step"] == "account_link"
