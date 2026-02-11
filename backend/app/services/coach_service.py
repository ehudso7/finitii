"""Coach service: Explain, Execute, Plan, Review, and Recap modes.

Phase 2 modes:
- Explain: returns explanation of an entity (template-based)
- Execute: triggers an action (start a cheat code run)

Phase 6 modes:
- Plan: generates max-3-step action plan based on goals, recommendations, forecast
- Review: wins → one improvement → next move
- Recap: weekly summary of activity, spending, and progress

All modes are template-based — no free-form chat, no LLM generation.
All interactions audit-logged.
Coach memory (tone, aggressiveness) personalizes output when ai_memory consent granted.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeDefinition,
    CheatCodeOutcome,
    CheatCodeRun,
    Recommendation,
    RunStatus,
)
from app.models.coach_memory import CoachAggressiveness, CoachTone
from app.models.forecast import ForecastSnapshot
from app.models.goal import Goal
from app.models.recurring import RecurringPattern, Confidence
from app.models.merchant import Merchant
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.services import audit_service, coach_memory_service
from app.services.recurring_service import INTERVAL_TOLERANCE_DAYS


# --- Phase 2 explanation templates ---

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


# --- Phase 6 plan templates ---

PLAN_TEMPLATES = {
    "goal_focused": (
        "{tone_opener}Based on your goal \"{goal_title}\", here's your action plan:"
    ),
    "urgency_focused": (
        "{tone_opener}Your financial urgency score is {urgency}/100. "
        "Here's a focused plan to improve your situation:"
    ),
    "general": (
        "{tone_opener}Here's your personalized action plan based on your "
        "current financial snapshot:"
    ),
}

PLAN_STEP_TEMPLATES = {
    "start_recommendation": (
        "Start \"{title}\" — {explanation} "
        "(~{minutes} min, confidence: {confidence})"
    ),
    "resume_run": (
        "Resume \"{title}\" — you have {remaining} steps left "
        "({completed}/{total} completed)"
    ),
    "review_bills": (
        "Review your {bill_count} recurring bills (${monthly_total}/month). "
        "Look for non-essential charges to reduce."
    ),
    "check_forecast": (
        "Check your forecast: safe-to-spend today is ${sts_today}. "
        "{forecast_note}"
    ),
    "set_goal": (
        "Set a financial goal to guide your next moves. "
        "Goals help us recommend the most relevant cheat codes."
    ),
}


# --- Phase 6 review templates ---

REVIEW_TEMPLATES = {
    "with_wins": (
        "{tone_opener}"
        "Wins: {wins_summary} "
        "Improvement area: {improvement} "
        "Next move: {next_move}"
    ),
    "no_wins": (
        "{tone_opener}"
        "You haven't completed any cheat codes yet — that's okay! "
        "Improvement area: {improvement} "
        "Next move: {next_move}"
    ),
}


# --- Phase 6 recap templates ---

RECAP_TEMPLATES = {
    "active_week": (
        "{tone_opener}Weekly Recap ({period}): "
        "Spending: ${total_spent} across {txn_count} transactions. "
        "{top_category_note}"
        "Cheat codes: {run_progress} "
        "{forecast_note}"
        "{goal_note}"
    ),
    "quiet_week": (
        "{tone_opener}Weekly Recap ({period}): "
        "Spending: ${total_spent} across {txn_count} transactions. "
        "{top_category_note}"
        "No cheat code activity this week. "
        "{forecast_note}"
        "{goal_note}"
    ),
}


# --- Tone openers by tone + aggressiveness ---

TONE_OPENERS = {
    (CoachTone.encouraging, CoachAggressiveness.conservative): "Great progress! ",
    (CoachTone.encouraging, CoachAggressiveness.moderate): "You're doing well! ",
    (CoachTone.encouraging, CoachAggressiveness.aggressive): "Let's keep the momentum going! ",
    (CoachTone.direct, CoachAggressiveness.conservative): "",
    (CoachTone.direct, CoachAggressiveness.moderate): "Here's what matters: ",
    (CoachTone.direct, CoachAggressiveness.aggressive): "Action needed: ",
    (CoachTone.neutral, CoachAggressiveness.conservative): "",
    (CoachTone.neutral, CoachAggressiveness.moderate): "",
    (CoachTone.neutral, CoachAggressiveness.aggressive): "",
}

# Default tone/aggressiveness when no coach memory or no consent
DEFAULT_TONE = CoachTone.neutral
DEFAULT_AGGRESSIVENESS = CoachAggressiveness.moderate


# --- Helpers ---

def _get_tone_opener(tone: CoachTone, aggressiveness: CoachAggressiveness) -> str:
    """Get personalized tone opener based on coach memory settings."""
    return TONE_OPENERS.get((tone, aggressiveness), "")


async def _get_coach_prefs(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[CoachTone, CoachAggressiveness]:
    """Get coach tone and aggressiveness. Falls back to defaults without consent."""
    memory = await coach_memory_service.get_memory(db, user_id=user_id)
    if memory is not None:
        return memory.tone, memory.aggressiveness
    return DEFAULT_TONE, DEFAULT_AGGRESSIVENESS


# --- Phase 2: Explain mode ---

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


# --- Phase 2: Execute mode ---

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
    """
    from app.services import cheat_code_service

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


# --- Phase 6: Plan mode ---

async def plan(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Generate a max-3-step action plan based on goals, recommendations, forecast.

    Template-based. Coach memory personalizes tone if ai_memory consent granted.
    Returns: {mode, response, steps, template_used, inputs, caveats}
    """
    tone, aggressiveness = await _get_coach_prefs(db, user_id)
    tone_opener = _get_tone_opener(tone, aggressiveness)

    # Gather context
    goals = await _get_active_goals(db, user_id)
    recommendations = await _get_recommendations(db, user_id)
    paused_runs = await _get_runs_by_status(db, user_id, RunStatus.paused)
    in_progress_runs = await _get_runs_by_status(db, user_id, RunStatus.in_progress)
    forecast = await _get_latest_forecast(db, user_id)
    bills = await _get_active_bills(db, user_id)

    steps: list[dict] = []
    caveats: list[str] = []
    template_key = "general"
    template_inputs: dict = {"tone_opener": tone_opener}

    # Priority 1: Resume paused runs (max 1 step)
    if paused_runs:
        run = paused_runs[0]
        defn = await _get_definition(db, run.cheat_code_id)
        if defn:
            steps.append({
                "step_number": len(steps) + 1,
                "action": "resume_run",
                "title": f"Resume \"{defn.title}\"",
                "description": PLAN_STEP_TEMPLATES["resume_run"].format(
                    title=defn.title,
                    remaining=run.total_steps - run.completed_steps,
                    completed=run.completed_steps,
                    total=run.total_steps,
                ),
            })

    # Priority 2: Start top recommendations (fill remaining steps)
    for rec in recommendations:
        if len(steps) >= 3:
            break
        # Skip if user already has an in-progress or paused run for this code
        already_running = any(
            r.cheat_code_id == rec.cheat_code_id
            for r in in_progress_runs + paused_runs
        )
        if already_running:
            continue
        defn = await _get_definition(db, rec.cheat_code_id)
        if defn:
            steps.append({
                "step_number": len(steps) + 1,
                "action": "start_recommendation",
                "title": f"Start \"{defn.title}\"",
                "description": PLAN_STEP_TEMPLATES["start_recommendation"].format(
                    title=defn.title,
                    explanation=rec.explanation,
                    minutes=defn.estimated_minutes,
                    confidence=rec.confidence,
                ),
            })

    # Priority 3: Review bills if user has them and still room
    if len(steps) < 3 and bills:
        monthly_total = _estimate_monthly_total(bills)
        steps.append({
            "step_number": len(steps) + 1,
            "action": "review_bills",
            "title": "Review recurring bills",
            "description": PLAN_STEP_TEMPLATES["review_bills"].format(
                bill_count=len(bills),
                monthly_total=str(round(monthly_total, 2)),
            ),
        })

    # Priority 4: Check forecast if available and still room
    if len(steps) < 3 and forecast:
        forecast_note = ""
        if forecast.safe_to_spend_week is not None:
            if forecast.safe_to_spend_week < 0:
                forecast_note = "Your weekly outlook is negative — focus on reducing spending."
            else:
                forecast_note = f"You have ${forecast.safe_to_spend_week} safe to spend this week."

        steps.append({
            "step_number": len(steps) + 1,
            "action": "check_forecast",
            "title": "Review your forecast",
            "description": PLAN_STEP_TEMPLATES["check_forecast"].format(
                sts_today=str(forecast.safe_to_spend_today),
                forecast_note=forecast_note,
            ),
        })

    # Priority 5: Set goals if none exist and still room
    if len(steps) < 3 and not goals:
        steps.append({
            "step_number": len(steps) + 1,
            "action": "set_goal",
            "title": "Set a financial goal",
            "description": PLAN_STEP_TEMPLATES["set_goal"],
        })

    # Ensure max 3 steps
    steps = steps[:3]

    # Determine plan template
    if goals:
        template_key = "goal_focused"
        template_inputs["goal_title"] = goals[0].title
    elif forecast and forecast.urgency_score >= 50:
        template_key = "urgency_focused"
        template_inputs["urgency"] = forecast.urgency_score
    else:
        template_key = "general"

    plan_template = PLAN_TEMPLATES[template_key]
    response = plan_template.format(**template_inputs)

    # Append step summaries to response
    for s in steps:
        response += f"\n{s['step_number']}. {s['title']}: {s['description']}"

    if not steps:
        response += "\nNo actions available right now. Link an account and set a goal to get started."
        caveats.append("No recommendations or data available to build a plan.")

    # Aggressiveness affects caveats
    if aggressiveness == CoachAggressiveness.conservative:
        caveats.append("Take your time — there's no rush to complete all steps at once.")
    elif aggressiveness == CoachAggressiveness.aggressive:
        caveats.append("Try to complete at least one step today for maximum impact.")

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="coach.plan",
        entity_type="Coach",
        entity_id=user_id,
        action="plan",
        detail={
            "template_used": template_key,
            "step_count": len(steps),
            "step_actions": [s["action"] for s in steps],
            "tone": tone.value,
            "aggressiveness": aggressiveness.value,
        },
        ip_address=ip_address,
    )

    return {
        "mode": "plan",
        "response": response,
        "steps": steps,
        "template_used": template_key,
        "inputs": template_inputs,
        "caveats": caveats,
    }


# --- Phase 6: Review mode ---

async def review(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Review: wins → one improvement → next move.

    Template-based. Audit-logged.
    Returns: {mode, response, template_used, inputs, caveats}
    """
    tone, aggressiveness = await _get_coach_prefs(db, user_id)
    tone_opener = _get_tone_opener(tone, aggressiveness)

    # Gather wins: completed runs with outcomes
    completed_runs = await _get_runs_by_status(db, user_id, RunStatus.completed)
    archived_runs = await _get_runs_by_status(db, user_id, RunStatus.archived)
    all_done_runs = completed_runs + archived_runs

    wins: list[dict] = []
    total_savings = Decimal("0.00")
    for run in all_done_runs:
        defn = await _get_definition(db, run.cheat_code_id)
        outcome = await _get_outcome_for_run(db, run.id)
        win_entry: dict = {
            "title": defn.title if defn else "Unknown",
            "code_id": str(run.cheat_code_id),
        }
        if outcome and outcome.reported_savings:
            win_entry["savings"] = str(outcome.reported_savings)
            total_savings += outcome.reported_savings
        wins.append(win_entry)

    # Build wins summary
    if wins:
        wins_summary = f"You've completed {len(wins)} cheat code(s)"
        if total_savings > 0:
            wins_summary += f", saving ${total_savings} total"
        wins_summary += "."
        template_key = "with_wins"
    else:
        wins_summary = ""
        template_key = "no_wins"

    # Identify one improvement area
    improvement = await _identify_improvement(db, user_id)

    # Identify next move
    next_move = await _identify_next_move(db, user_id)

    template_inputs = {
        "tone_opener": tone_opener,
        "wins_summary": wins_summary,
        "improvement": improvement,
        "next_move": next_move,
    }

    review_template = REVIEW_TEMPLATES[template_key]
    response = review_template.format(**template_inputs)

    caveats: list[str] = []
    if not wins:
        caveats.append("Complete a cheat code to see your wins here.")

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="coach.review",
        entity_type="Coach",
        entity_id=user_id,
        action="review",
        detail={
            "template_used": template_key,
            "wins_count": len(wins),
            "total_savings": str(total_savings),
            "tone": tone.value,
            "aggressiveness": aggressiveness.value,
        },
        ip_address=ip_address,
    )

    return {
        "mode": "review",
        "response": response,
        "wins": wins,
        "template_used": template_key,
        "inputs": template_inputs,
        "caveats": caveats,
    }


# --- Phase 6: Weekly Recap ---

async def recap(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Generate weekly recap: spending, cheat code progress, forecast, goals.

    Template-based. Audit-logged.
    Returns: {mode, response, template_used, inputs, caveats}
    """
    tone, aggressiveness = await _get_coach_prefs(db, user_id)
    tone_opener = _get_tone_opener(tone, aggressiveness)

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    period = f"{week_ago.strftime('%b %d')}–{now.strftime('%b %d')}"

    # Spending this week
    txn_result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.debit,
            Transaction.transaction_date >= week_ago,
        )
    )
    week_txns = list(txn_result.scalars().all())
    total_spent = sum(t.amount for t in week_txns)
    txn_count = len(week_txns)

    # Top spending category
    category_spend: dict[str, Decimal] = defaultdict(Decimal)
    category_ids = {t.category_id for t in week_txns if t.category_id}
    categories_map: dict[uuid.UUID, str] = {}
    if category_ids:
        cat_result = await db.execute(
            select(Category).where(Category.id.in_(category_ids))
        )
        for cat in cat_result.scalars().all():
            categories_map[cat.id] = cat.name

    for txn in week_txns:
        if txn.category_id and txn.category_id in categories_map:
            category_spend[categories_map[txn.category_id]] += txn.amount

    top_category_note = ""
    if category_spend:
        top_cat = max(category_spend, key=lambda k: category_spend[k])
        top_amount = category_spend[top_cat]
        top_category_note = f"Top category: {top_cat} (${top_amount}). "

    # Cheat code progress this week
    run_result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.user_id == user_id,
            CheatCodeRun.status.in_([
                RunStatus.in_progress,
                RunStatus.completed,
                RunStatus.paused,
            ]),
        )
    )
    all_runs = list(run_result.scalars().all())

    # Count runs completed this week
    completed_this_week = [
        r for r in all_runs
        if r.status == RunStatus.completed
        and r.completed_at
        and _ensure_tz(r.completed_at) >= week_ago
    ]
    in_progress = [r for r in all_runs if r.status == RunStatus.in_progress]

    has_run_activity = bool(completed_this_week or in_progress)

    run_progress = ""
    if completed_this_week:
        run_progress += f"{len(completed_this_week)} completed this week. "
    if in_progress:
        run_progress += f"{len(in_progress)} in progress. "
    if not run_progress:
        run_progress = "No cheat code activity this week. "

    # Forecast note
    forecast = await _get_latest_forecast(db, user_id)
    forecast_note = ""
    if forecast:
        forecast_note = (
            f"Forecast: safe-to-spend today ${forecast.safe_to_spend_today}, "
            f"confidence: {forecast.confidence.value}. "
        )

    # Goal progress
    goals = await _get_active_goals(db, user_id)
    goal_note = ""
    if goals:
        goal_titles = [g.title for g in goals[:3]]
        goal_note = f"Active goals: {', '.join(goal_titles)}."
    else:
        goal_note = "No active goals set."

    template_key = "active_week" if has_run_activity else "quiet_week"

    template_inputs = {
        "tone_opener": tone_opener,
        "period": period,
        "total_spent": str(total_spent),
        "txn_count": txn_count,
        "top_category_note": top_category_note,
        "run_progress": run_progress,
        "forecast_note": forecast_note,
        "goal_note": goal_note,
    }

    recap_template = RECAP_TEMPLATES[template_key]
    response = recap_template.format(**template_inputs)

    caveats: list[str] = []
    if txn_count == 0:
        caveats.append("No transactions recorded this week — data may be incomplete.")

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="coach.recap",
        entity_type="Coach",
        entity_id=user_id,
        action="recap",
        detail={
            "template_used": template_key,
            "period": period,
            "total_spent": str(total_spent),
            "txn_count": txn_count,
            "runs_completed": len(completed_this_week),
            "runs_in_progress": len(in_progress),
            "tone": tone.value,
            "aggressiveness": aggressiveness.value,
        },
        ip_address=ip_address,
    )

    return {
        "mode": "recap",
        "response": response,
        "template_used": template_key,
        "inputs": template_inputs,
        "caveats": caveats,
    }


# --- Private explain helpers (Phase 2) ---

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


# --- Private helpers for Plan/Review/Recap ---

def _ensure_tz(dt: datetime) -> datetime:
    """SQLite returns naive datetimes — normalize to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_active_goals(db: AsyncSession, user_id: uuid.UUID) -> list[Goal]:
    result = await db.execute(
        select(Goal).where(
            Goal.user_id == user_id,
            Goal.is_active == True,  # noqa: E712
        ).order_by(Goal.priority.asc(), Goal.created_at.asc())
    )
    return list(result.scalars().all())


async def _get_recommendations(
    db: AsyncSession, user_id: uuid.UUID
) -> list[Recommendation]:
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.user_id == user_id)
        .order_by(Recommendation.rank.asc())
    )
    return list(result.scalars().all())


async def _get_runs_by_status(
    db: AsyncSession, user_id: uuid.UUID, status: RunStatus
) -> list[CheatCodeRun]:
    result = await db.execute(
        select(CheatCodeRun).where(
            CheatCodeRun.user_id == user_id,
            CheatCodeRun.status == status,
        ).order_by(CheatCodeRun.started_at.desc())
    )
    return list(result.scalars().all())


async def _get_latest_forecast(
    db: AsyncSession, user_id: uuid.UUID
) -> ForecastSnapshot | None:
    result = await db.execute(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.user_id == user_id)
        .order_by(ForecastSnapshot.computed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_active_bills(
    db: AsyncSession, user_id: uuid.UUID
) -> list[RecurringPattern]:
    result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def _get_definition(
    db: AsyncSession, cheat_code_id: uuid.UUID
) -> CheatCodeDefinition | None:
    result = await db.execute(
        select(CheatCodeDefinition).where(CheatCodeDefinition.id == cheat_code_id)
    )
    return result.scalar_one_or_none()


async def _get_outcome_for_run(
    db: AsyncSession, run_id: uuid.UUID
) -> CheatCodeOutcome | None:
    result = await db.execute(
        select(CheatCodeOutcome).where(CheatCodeOutcome.run_id == run_id)
    )
    return result.scalar_one_or_none()


def _estimate_monthly_total(bills: list[RecurringPattern]) -> Decimal:
    """Estimate monthly total from recurring patterns."""
    FREQ_TO_MONTHLY = {
        "weekly": Decimal("4.33"),
        "biweekly": Decimal("2.17"),
        "monthly": Decimal("1"),
        "quarterly": Decimal("0.33"),
        "annual": Decimal("0.083"),
    }
    total = Decimal("0.00")
    for bill in bills:
        if bill.estimated_amount:
            freq = bill.frequency.value if bill.frequency else "monthly"
            multiplier = FREQ_TO_MONTHLY.get(freq, Decimal("1"))
            total += bill.estimated_amount * multiplier
    return total


async def _identify_improvement(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Identify one area for improvement based on data signals."""
    # Check forecast urgency
    forecast = await _get_latest_forecast(db, user_id)
    if forecast and forecast.urgency_score >= 60:
        return (
            f"Your urgency score is {forecast.urgency_score}/100. "
            "Focus on reducing non-essential spending this week."
        )

    # Check if safe-to-spend is low/negative
    if forecast and forecast.safe_to_spend_today is not None:
        if forecast.safe_to_spend_today < 0:
            return (
                f"Your safe-to-spend today is ${forecast.safe_to_spend_today} (negative). "
                "Consider pausing discretionary spending."
            )

    # Check for paused runs
    paused = await _get_runs_by_status(db, user_id, RunStatus.paused)
    if paused:
        return (
            f"You have {len(paused)} paused cheat code(s). "
            "Resuming one could help you make progress."
        )

    # Default: encourage goal-setting or consistency
    goals = await _get_active_goals(db, user_id)
    if not goals:
        return "Set a financial goal to guide your cheat code recommendations."

    return "Keep consistent with your current cheat codes for best results."


async def _identify_next_move(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Identify the single best next action."""
    # Check for paused runs first
    paused = await _get_runs_by_status(db, user_id, RunStatus.paused)
    if paused:
        defn = await _get_definition(db, paused[0].cheat_code_id)
        title = defn.title if defn else "your paused cheat code"
        return f"Resume \"{title}\" to pick up where you left off."

    # Check for top recommendation
    recs = await _get_recommendations(db, user_id)
    if recs:
        defn = await _get_definition(db, recs[0].cheat_code_id)
        if defn:
            return (
                f"Start \"{defn.title}\" — your #1 recommendation "
                f"(~{defn.estimated_minutes} min)."
            )

    return "Link an account or set a goal to get personalized recommendations."
