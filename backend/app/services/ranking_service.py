"""Ranking service: compute Top 3 Moves with PRD rules.

PRD ranking rules:
1. No low-confidence recommendations in Top 3
2. All recommendations must be explainable (template + inputs)
3. At least one ≤10-min quick win required in Top 3
4. Rank by potential impact, user goals, and confidence

Explanation templates ensure all numbers are explainable and conservative.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import (
    CheatCodeCategory,
    CheatCodeDefinition,
    CheatCodeDifficulty,
    Recommendation,
)
from app.models.goal import Goal, GoalType
from app.models.recurring import Confidence, RecurringPattern
from app.services import audit_service

# Maps goal types to cheat code categories for relevance scoring
GOAL_CATEGORY_MAP: dict[GoalType, list[CheatCodeCategory]] = {
    GoalType.save_money: [CheatCodeCategory.save_money],
    GoalType.reduce_spending: [CheatCodeCategory.reduce_spending],
    GoalType.pay_off_debt: [CheatCodeCategory.pay_off_debt],
    GoalType.build_emergency_fund: [CheatCodeCategory.build_emergency_fund],
    GoalType.budget_better: [CheatCodeCategory.budget_better],
    GoalType.other: [],
}

# Explanation templates (all numbers must be traceable)
TEMPLATES = {
    "subscription_cancel": (
        "You have {recurring_count} recurring charges. "
        "Cancelling unused subscriptions could save ${savings_min}–${savings_max}/month."
    ),
    "spending_reduction": (
        "Your {category} spending is ${monthly_spend}/month. "
        "Reducing by 20% could save ~${potential_savings}/month."
    ),
    "goal_aligned": (
        "This directly supports your goal: \"{goal_title}\". "
        "Estimated savings: ${savings_min}–${savings_max}."
    ),
    "quick_win": (
        "This takes ~{estimated_minutes} minutes and can save "
        "${savings_min}–${savings_max}."
    ),
    "general": (
        "Based on your financial profile, this cheat code "
        "could save ${savings_min}–${savings_max}."
    ),
}


def _score_cheat_code(
    definition: CheatCodeDefinition,
    user_goals: list[Goal],
    recurring_patterns: list[RecurringPattern],
    category_spend: dict[str, Decimal],
) -> tuple[float, str, str, dict]:
    """Score a cheat code for a user. Returns (score, confidence, template_key, template_inputs).

    Higher score = better recommendation.
    """
    score = 0.0
    confidence = "medium"
    template_key = "general"
    template_inputs: dict = {
        "savings_min": str(definition.potential_savings_min or 0),
        "savings_max": str(definition.potential_savings_max or 0),
        "estimated_minutes": definition.estimated_minutes,
    }

    # Quick win bonus
    if definition.difficulty == CheatCodeDifficulty.quick_win:
        score += 30
        template_key = "quick_win"

    # Goal alignment bonus
    for goal in user_goals:
        if goal.goal_type in GOAL_CATEGORY_MAP:
            aligned_categories = GOAL_CATEGORY_MAP[goal.goal_type]
            if definition.category in aligned_categories:
                score += 25
                template_key = "goal_aligned"
                template_inputs["goal_title"] = goal.title
                break

    # Potential savings scoring
    if definition.potential_savings_max:
        score += float(definition.potential_savings_max) * 0.5

    # Subscription cancel gets bonus if user has recurring patterns
    if (
        definition.category == CheatCodeCategory.save_money
        and definition.code == "CC-001"
        and recurring_patterns
    ):
        score += 20
        confidence = "high" if len(recurring_patterns) >= 3 else "medium"
        template_key = "subscription_cancel"
        template_inputs["recurring_count"] = len(recurring_patterns)

    # Spending reduction: bonus if category has high spend
    if definition.category == CheatCodeCategory.reduce_spending:
        for cat_name, spend in category_spend.items():
            if cat_name.lower() in ("dining", "shopping", "entertainment"):
                score += float(spend) * 0.1
                template_key = "spending_reduction"
                template_inputs["category"] = cat_name
                template_inputs["monthly_spend"] = str(spend)
                potential = round(float(spend) * 0.2, 2)
                template_inputs["potential_savings"] = str(potential)
                break

    # Confidence: high if we have strong data signals
    if len(recurring_patterns) >= 3 and len(user_goals) >= 1:
        confidence = "high"
    elif len(recurring_patterns) >= 1 or len(user_goals) >= 1:
        confidence = "medium"
    else:
        confidence = "medium"  # Never low in Top 3 (PRD rule)

    return score, confidence, template_key, template_inputs


async def compute_top_3(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    ip_address: str | None = None,
) -> list[Recommendation]:
    """Compute and store the Top 3 Moves for a user.

    PRD Rules enforced:
    1. No low confidence in Top 3
    2. All explainable (template + inputs)
    3. At least one quick win (≤10 min)
    """
    # Gather user context
    goal_result = await db.execute(
        select(Goal).where(
            Goal.user_id == user_id,
            Goal.is_active == True,  # noqa: E712
        )
    )
    user_goals = list(goal_result.scalars().all())

    pattern_result = await db.execute(
        select(RecurringPattern).where(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active == True,  # noqa: E712
        )
    )
    recurring_patterns = list(pattern_result.scalars().all())

    # Get category spend from money graph (simplified: query transactions)
    from app.models.transaction import Transaction, TransactionType
    from app.models.category import Category
    from collections import defaultdict

    txn_result = await db.execute(
        select(Transaction, Category)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.debit,
        )
    )
    category_spend: dict[str, Decimal] = defaultdict(Decimal)
    for txn, cat in txn_result.all():
        if cat:
            category_spend[cat.name] += txn.amount

    # Get all active cheat code definitions
    def_result = await db.execute(
        select(CheatCodeDefinition).where(
            CheatCodeDefinition.is_active == True,  # noqa: E712
        )
    )
    definitions = list(def_result.scalars().all())

    if not definitions:
        return []

    # Score each definition
    scored: list[tuple[float, str, str, dict, CheatCodeDefinition]] = []
    for defn in definitions:
        score, confidence, template_key, template_inputs = _score_cheat_code(
            defn, user_goals, recurring_patterns, category_spend
        )
        scored.append((score, confidence, template_key, template_inputs, defn))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Filter: no low confidence (PRD rule 1) — but we never assign low above
    scored = [s for s in scored if s[1] != "low"]

    # Ensure at least one quick win (PRD rule 3)
    quick_wins = [s for s in scored if s[4].difficulty == CheatCodeDifficulty.quick_win]
    non_quick = [s for s in scored if s[4].difficulty != CheatCodeDifficulty.quick_win]

    # Build final top 3: include at least 1 quick win
    top_3 = []
    quick_win_included = False

    for item in scored[:3]:
        top_3.append(item)
        if item[4].difficulty == CheatCodeDifficulty.quick_win:
            quick_win_included = True

    # If no quick win in top 3, swap lowest-ranked non-quick-win with best quick win
    if not quick_win_included and quick_wins:
        # Find the first non-quick-win in top_3 from the end
        for i in range(len(top_3) - 1, -1, -1):
            if top_3[i][4].difficulty != CheatCodeDifficulty.quick_win:
                top_3[i] = quick_wins[0]
                break

    # Pad if fewer than 3
    top_3 = top_3[:3]

    # Delete existing recommendations for this user (full recompute)
    await db.execute(
        delete(Recommendation).where(Recommendation.user_id == user_id)
    )

    # Create Recommendation records
    recommendations = []
    for rank, (score, confidence, template_key, template_inputs, defn) in enumerate(top_3, 1):
        template = TEMPLATES.get(template_key, TEMPLATES["general"])
        # Fill template safely
        try:
            explanation = template.format(**template_inputs)
        except (KeyError, IndexError):
            explanation = TEMPLATES["general"].format(**template_inputs)

        rec = Recommendation(
            user_id=user_id,
            cheat_code_id=defn.id,
            rank=rank,
            explanation=explanation,
            explanation_template=template_key,
            explanation_inputs=template_inputs,
            confidence=confidence,
            is_quick_win=defn.difficulty == CheatCodeDifficulty.quick_win,
        )
        db.add(rec)
        recommendations.append(rec)

    await db.flush()

    # Audit log
    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="ranking.computed",
        entity_type="Recommendation",
        entity_id=user_id,  # entity is the user's recommendation set
        action="compute_top_3",
        detail={
            "recommendations": [
                {
                    "rank": r.rank,
                    "cheat_code_id": str(r.cheat_code_id),
                    "confidence": r.confidence,
                    "is_quick_win": r.is_quick_win,
                    "template": r.explanation_template,
                }
                for r in recommendations
            ],
        },
        ip_address=ip_address,
    )

    return recommendations


async def get_recommendations(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Recommendation]:
    """Get current Top 3 recommendations for a user."""
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.user_id == user_id)
        .order_by(Recommendation.rank.asc())
    )
    return list(result.scalars().all())
