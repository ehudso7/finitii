"""Coach service: Explain + Execute modes only (Phase 2).

- Explain mode: returns explanation of an entity (transaction, recurring pattern, recommendation)
- Execute mode: triggers an action (start a cheat code run, complete a step)

Template-based only — no free-text LLM generation in Phase 2.
All interactions audit-logged.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeDefinition, CheatCodeRun, Recommendation
from app.models.recurring import RecurringPattern, Confidence
from app.models.merchant import Merchant
from app.models.category import Category
from app.services import audit_service, cheat_code_service
from app.services.recurring_service import INTERVAL_TOLERANCE_DAYS, AMOUNT_TOLERANCE_FRACTION


# Explanation templates by context type
EXPLAIN_TEMPLATES = {
    "recurring_pattern": (
        "This is a {frequency} charge of ~${amount} to {merchant}. "
        "Confidence: {confidence}. "
        "We detected this because you have {occurrences} similar transactions "
        "at regular intervals (±{tolerance_days} days). "
        "{confidence_note}"
    ),
    "recommendation": (
        "We recommend \"{title}\" (rank #{rank}). "
        "{explanation} "
        "Confidence: {confidence}. "
        "This is{quick_win_note} estimated to take ~{minutes} minutes."
    ),
    "transaction": (
        "This transaction of ${amount} was categorized as \"{category}\" "
        "at {merchant}. {categorization_note}"
    ),
    "cheat_code": (
        "\"{title}\": {description} "
        "Difficulty: {difficulty}. Estimated time: ~{minutes} minutes. "
        "{savings_note}"
    ),
}

CONFIDENCE_NOTES = {
    "high": "High confidence — consistent amounts and timing.",
    "medium": "Medium confidence — some variation in amounts or timing.",
    "low": "Low confidence — limited data or inconsistent patterns.",
}

EXECUTE_ACTIONS = {
    "start_run": "Start a cheat code run from a recommendation.",
    "complete_step": "Complete a step in an active cheat code run.",
}


async def explain(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    context_type: str,
    context_id: uuid.UUID,
    question: str | None = None,
    ip_address: str | None = None,
) -> dict:
    """Explain an entity to the user (template-based).

    Returns: {mode, response, template_used, inputs, caveats}
    """
    caveats: list[str] = []

    if context_type == "recurring_pattern":
        response, template, inputs, caveats = await _explain_recurring(
            db, user_id, context_id
        )
    elif context_type == "recommendation":
        response, template, inputs, caveats = await _explain_recommendation(
            db, user_id, context_id
        )
    elif context_type == "cheat_code":
        response, template, inputs, caveats = await _explain_cheat_code(
            db, context_id
        )
    else:
        response = f"Explanation not available for context type: {context_type}"
        template = "unknown"
        inputs = {"context_type": context_type}
        caveats = ["This context type is not supported in the current version."]

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="coach.explain",
        entity_type=context_type,
        entity_id=context_id,
        action="explain",
        detail={
            "template_used": template,
            "question": question,
        },
        ip_address=ip_address,
    )

    return {
        "mode": "explain",
        "response": response,
        "template_used": template,
        "inputs": inputs,
        "caveats": caveats,
    }


async def execute(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    context_type: str,
    context_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Execute an action (template-based, Phase 2).

    Supported actions:
    - context_type="recommendation": starts a run
    - context_type="step": completes a step (context_id=run_id, step_number from context)
    """
    if context_type == "recommendation":
        run = await cheat_code_service.start_run(
            db,
            user_id=user_id,
            recommendation_id=context_id,
            ip_address=ip_address,
        )
        response = f"Started cheat code run. {run.total_steps} steps to complete."
        template = "execute_start_run"
        inputs = {
            "run_id": str(run.id),
            "total_steps": run.total_steps,
        }
    else:
        response = f"Execute not available for context type: {context_type}"
        template = "unknown"
        inputs = {"context_type": context_type}

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="coach.execute",
        entity_type=context_type,
        entity_id=context_id,
        action="execute",
        detail={
            "template_used": template,
        },
        ip_address=ip_address,
    )

    return {
        "mode": "execute",
        "response": response,
        "template_used": template,
        "inputs": inputs,
        "caveats": [],
    }


async def _explain_recurring(
    db: AsyncSession,
    user_id: uuid.UUID,
    pattern_id: uuid.UUID,
) -> tuple[str, str, dict, list[str]]:
    """Build explanation for a recurring pattern."""
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.id == pattern_id,
            RecurringPattern.user_id == user_id,
        )
    )
    pattern = result.scalar_one()

    # Get merchant name
    merchant_name = "Unknown"
    if pattern.merchant_id:
        m_result = await db.execute(
            select(Merchant).where(Merchant.id == pattern.merchant_id)
        )
        merchant = m_result.scalar_one_or_none()
        if merchant:
            merchant_name = merchant.display_name

    confidence_note = CONFIDENCE_NOTES.get(pattern.confidence.value, "")

    inputs = {
        "frequency": pattern.frequency.value,
        "amount": str(pattern.estimated_amount),
        "merchant": merchant_name,
        "confidence": pattern.confidence.value,
        "occurrences": "multiple",  # We don't store exact count on pattern
        "tolerance_days": INTERVAL_TOLERANCE_DAYS,
        "confidence_note": confidence_note,
    }

    template = EXPLAIN_TEMPLATES["recurring_pattern"]
    response = template.format(**inputs)

    caveats = []
    if pattern.confidence == Confidence.medium:
        caveats.append("Pattern confidence is medium — may change with more data.")
    elif pattern.confidence == Confidence.low:
        caveats.append("Pattern confidence is low — treat as approximate.")

    return response, "recurring_pattern", inputs, caveats


async def _explain_recommendation(
    db: AsyncSession,
    user_id: uuid.UUID,
    recommendation_id: uuid.UUID,
) -> tuple[str, str, dict, list[str]]:
    """Build explanation for a recommendation."""
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == user_id,
        )
    )
    rec = result.scalar_one()

    # Get cheat code definition
    def_result = await db.execute(
        select(CheatCodeDefinition).where(CheatCodeDefinition.id == rec.cheat_code_id)
    )
    definition = def_result.scalar_one()

    inputs = {
        "title": definition.title,
        "rank": rec.rank,
        "explanation": rec.explanation,
        "confidence": rec.confidence,
        "quick_win_note": " a quick win," if rec.is_quick_win else "",
        "minutes": definition.estimated_minutes,
    }

    template = EXPLAIN_TEMPLATES["recommendation"]
    response = template.format(**inputs)

    caveats = []
    if rec.confidence == "medium":
        caveats.append("Recommendation confidence is medium — based on available data.")

    return response, "recommendation", inputs, caveats


async def _explain_cheat_code(
    db: AsyncSession,
    cheat_code_id: uuid.UUID,
) -> tuple[str, str, dict, list[str]]:
    """Build explanation for a cheat code definition."""
    result = await db.execute(
        select(CheatCodeDefinition).where(CheatCodeDefinition.id == cheat_code_id)
    )
    definition = result.scalar_one()

    savings_note = ""
    if definition.potential_savings_min and definition.potential_savings_max:
        savings_note = (
            f"Potential savings: ${definition.potential_savings_min}"
            f"–${definition.potential_savings_max}."
        )

    inputs = {
        "title": definition.title,
        "description": definition.description,
        "difficulty": definition.difficulty.value,
        "minutes": definition.estimated_minutes,
        "savings_note": savings_note,
    }

    template = EXPLAIN_TEMPLATES["cheat_code"]
    response = template.format(**inputs)

    return response, "cheat_code", inputs, []
