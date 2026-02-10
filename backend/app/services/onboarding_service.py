"""Onboarding service: enforce gate flow, First Win hard gate.

Gate order: consent → account_link → goals → top_3 → first_win → completed.
Cannot skip steps. first_win requires starting + completing ≥1 cheat code step.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeRun, RunStatus, StepRun
from app.models.onboarding import OnboardingState, OnboardingStep
from app.services import audit_service


# Ordered gate sequence
GATE_ORDER = [
    OnboardingStep.consent,
    OnboardingStep.account_link,
    OnboardingStep.goals,
    OnboardingStep.top_3,
    OnboardingStep.first_win,
    OnboardingStep.completed,
]

# Map step to its timestamp field
STEP_TIMESTAMP_FIELDS = {
    OnboardingStep.consent: "consent_completed_at",
    OnboardingStep.account_link: "account_completed_at",
    OnboardingStep.goals: "goals_completed_at",
    OnboardingStep.top_3: "top_3_completed_at",
    OnboardingStep.first_win: "first_win_completed_at",
}


async def get_or_create_state(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> OnboardingState:
    """Get or create the onboarding state for a user."""
    result = await db.execute(
        select(OnboardingState).where(OnboardingState.user_id == user_id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = OnboardingState(
            user_id=user_id,
            current_step=OnboardingStep.consent,
        )
        db.add(state)
        await db.flush()
    return state


async def advance_step(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    completed_step: OnboardingStep,
    ip_address: str | None = None,
) -> OnboardingState:
    """Complete the current gate and advance to the next step.

    Enforces:
    1. Steps must be completed in order (no skipping)
    2. first_win requires at least one completed cheat code step
    """
    state = await get_or_create_state(db, user_id)

    # Validate: the completed step must be the current step
    if state.current_step != completed_step:
        raise ValueError(
            f"Cannot complete step '{completed_step.value}': "
            f"current step is '{state.current_step.value}'"
        )

    # Special validation for first_win: must have at least 1 completed step in a run
    if completed_step == OnboardingStep.first_win:
        await _validate_first_win(db, user_id, state)

    # Set the timestamp for this step
    now = datetime.now(timezone.utc)
    timestamp_field = STEP_TIMESTAMP_FIELDS.get(completed_step)
    if timestamp_field:
        setattr(state, timestamp_field, now)

    # Advance to next step
    current_idx = GATE_ORDER.index(completed_step)
    if current_idx + 1 < len(GATE_ORDER):
        state.current_step = GATE_ORDER[current_idx + 1]

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="onboarding.step_completed",
        entity_type="OnboardingState",
        entity_id=state.id,
        action="advance",
        detail={
            "completed_step": completed_step.value,
            "new_step": state.current_step.value,
        },
        ip_address=ip_address,
    )

    return state


async def _validate_first_win(
    db: AsyncSession,
    user_id: uuid.UUID,
    state: OnboardingState,
) -> None:
    """Validate that the user has completed at least 1 step in a cheat code run.

    This is the hard gate: onboarding CANNOT complete without a First Win.
    """
    # Find any run with at least 1 completed step
    run_result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.user_id == user_id,
            CheatCodeRun.completed_steps >= 1,
        )
    )
    run = run_result.scalars().first()

    if run is None:
        raise ValueError(
            "Cannot complete first_win: must start a cheat code and complete at least 1 step"
        )

    # Record which run satisfied the first win
    state.first_win_cheat_code_run_id = run.id


async def get_state(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> OnboardingState:
    """Get the current onboarding state (creates if not exists)."""
    return await get_or_create_state(db, user_id)


async def is_onboarding_complete(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> bool:
    """Check if onboarding is fully completed."""
    state = await get_or_create_state(db, user_id)
    return state.current_step == OnboardingStep.completed
