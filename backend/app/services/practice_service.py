"""Practice service: scenario simulation, After-Action Review, Turn-into-Plan.

Key PRD rules:
1. Practice outputs ALWAYS have confidence capped at "medium"
2. Practice outputs CANNOT enter Top 3 without real-data corroboration
3. Simulator uses deterministic calculations (no LLM)
4. After-Action Review is template-based
5. "Turn into plan" bridges to coach plan mode
6. All interactions audit-logged
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.practice import (
    ScenarioDefinition,
    ScenarioRun,
    ScenarioRunStatus,
)
from app.services import audit_service


# Confidence is ALWAYS capped at medium for practice outputs (PRD rule)
PRACTICE_CONFIDENCE_CAP = "medium"


async def get_scenarios(
    db: AsyncSession,
    *,
    category: str | None = None,
) -> list[ScenarioDefinition]:
    """List all active scenarios, optionally filtered by category."""
    stmt = (
        select(ScenarioDefinition)
        .where(ScenarioDefinition.is_active == True)  # noqa: E712
        .order_by(ScenarioDefinition.display_order.asc())
    )
    if category:
        stmt = stmt.where(ScenarioDefinition.category == category)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_scenario(
    db: AsyncSession,
    *,
    scenario_id: uuid.UUID,
) -> ScenarioDefinition:
    """Get a single scenario by ID."""
    result = await db.execute(
        select(ScenarioDefinition).where(ScenarioDefinition.id == scenario_id)
    )
    return result.scalar_one()


async def start_scenario(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    scenario_id: uuid.UUID,
    ip_address: str | None = None,
) -> ScenarioRun:
    """Start a new scenario run. Multiple runs per scenario allowed."""
    scenario = await get_scenario(db, scenario_id=scenario_id)

    # Initialize with default slider values
    default_values = {}
    for slider in scenario.sliders:
        default_values[slider["key"]] = slider["default"]

    run = ScenarioRun(
        user_id=user_id,
        scenario_id=scenario_id,
        slider_values=default_values,
        confidence=PRACTICE_CONFIDENCE_CAP,
        status=ScenarioRunStatus.in_progress,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="practice.started",
        entity_type="ScenarioRun",
        entity_id=run.id,
        action="start",
        detail={
            "scenario_code": scenario.code,
            "scenario_title": scenario.title,
        },
        ip_address=ip_address,
    )

    return run


async def simulate(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    slider_values: dict,
    ip_address: str | None = None,
) -> ScenarioRun:
    """Run simulation with given slider values. Returns updated run with computed outcome.

    Validates slider values against scenario constraints.
    Computes deterministic outcome.
    Confidence is ALWAYS "medium" (PRD cap).
    """
    result = await db.execute(
        select(ScenarioRun).where(
            ScenarioRun.id == run_id,
            ScenarioRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status == ScenarioRunStatus.completed:
        raise ValueError("Run already completed. Start a new run to simulate again.")

    scenario = await get_scenario(db, scenario_id=run.scenario_id)

    # Validate slider values against scenario constraints
    validated = _validate_sliders(scenario.sliders, slider_values)

    # Compute outcome based on scenario + slider values
    outcome = _compute_outcome(scenario, validated)

    # Update run
    run.slider_values = validated
    run.computed_outcome = outcome
    run.confidence = PRACTICE_CONFIDENCE_CAP  # Always medium

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="practice.simulated",
        entity_type="ScenarioRun",
        entity_id=run.id,
        action="simulate",
        detail={
            "slider_values": validated,
            "confidence": PRACTICE_CONFIDENCE_CAP,
        },
        ip_address=ip_address,
    )

    return run


async def complete_scenario(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    ip_address: str | None = None,
) -> ScenarioRun:
    """Complete a scenario run and generate After-Action Review.

    AAR is template-based. Confidence capped at medium.
    """
    result = await db.execute(
        select(ScenarioRun).where(
            ScenarioRun.id == run_id,
            ScenarioRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status == ScenarioRunStatus.completed:
        raise ValueError("Run already completed.")

    if run.computed_outcome is None:
        raise ValueError("Must run simulation before completing.")

    scenario = await get_scenario(db, scenario_id=run.scenario_id)

    # Generate After-Action Review
    aar = _generate_after_action_review(scenario, run)

    run.after_action_review = aar
    run.status = ScenarioRunStatus.completed
    run.completed_at = datetime.now(timezone.utc)
    run.confidence = PRACTICE_CONFIDENCE_CAP

    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="practice.completed",
        entity_type="ScenarioRun",
        entity_id=run.id,
        action="complete",
        detail={
            "scenario_code": scenario.code,
            "has_aar": True,
            "confidence": PRACTICE_CONFIDENCE_CAP,
        },
        ip_address=ip_address,
    )

    return run


async def turn_into_plan(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    ip_address: str | None = None,
) -> dict:
    """Bridge practice output to coach plan. Returns plan steps derived from scenario.

    Does NOT feed into Top 3 ranking (PRD rule).
    Confidence capped at medium.
    """
    result = await db.execute(
        select(ScenarioRun).where(
            ScenarioRun.id == run_id,
            ScenarioRun.user_id == user_id,
        )
    )
    run = result.scalar_one()

    if run.status != ScenarioRunStatus.completed:
        raise ValueError("Must complete scenario before turning into plan.")

    scenario = await get_scenario(db, scenario_id=run.scenario_id)

    # Generate plan steps from practice outcome
    steps = _generate_plan_steps(scenario, run)

    # Mark that plan was generated
    run.plan_generated = True
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="practice.plan_generated",
        entity_type="ScenarioRun",
        entity_id=run.id,
        action="turn_into_plan",
        detail={
            "scenario_code": scenario.code,
            "step_count": len(steps),
            "confidence": PRACTICE_CONFIDENCE_CAP,
        },
        ip_address=ip_address,
    )

    return {
        "source": "practice",
        "scenario_title": scenario.title,
        "confidence": PRACTICE_CONFIDENCE_CAP,
        "steps": steps,
        "caveats": [
            "This plan is based on simulated data (confidence: medium).",
            "Results may differ with real financial data.",
            "Practice-derived plans do not affect your Top 3 recommendations.",
        ],
    }


async def get_user_runs(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    scenario_id: uuid.UUID | None = None,
) -> list[ScenarioRun]:
    """Get scenario runs for a user."""
    stmt = (
        select(ScenarioRun)
        .where(ScenarioRun.user_id == user_id)
        .order_by(ScenarioRun.started_at.desc())
    )
    if scenario_id:
        stmt = stmt.where(ScenarioRun.scenario_id == scenario_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ScenarioRun:
    """Get a specific scenario run."""
    result = await db.execute(
        select(ScenarioRun).where(
            ScenarioRun.id == run_id,
            ScenarioRun.user_id == user_id,
        )
    )
    return result.scalar_one()


# --- Private helpers ---


def _validate_sliders(
    slider_defs: list[dict], values: dict
) -> dict:
    """Validate and clamp slider values to defined ranges."""
    validated = {}
    slider_map = {s["key"]: s for s in slider_defs}

    for key, slider_def in slider_map.items():
        raw = values.get(key, slider_def["default"])
        # Clamp to range
        val = max(slider_def["min"], min(slider_def["max"], raw))
        validated[key] = val

    return validated


def _compute_outcome(scenario: ScenarioDefinition, slider_values: dict) -> dict:
    """Compute deterministic outcome from scenario initial state + slider values.

    Each scenario code has a specific computation logic.
    Returns outcome dict with computed values.
    """
    state = scenario.initial_state
    code = scenario.code

    if code == "S-001":  # Savings Rate Simulator
        monthly_savings = slider_values["monthly_savings"]
        expense_reduction = slider_values["expense_reduction"]
        total_monthly = monthly_savings + expense_reduction
        total_annual = total_monthly * 12
        current = state["current_savings"]
        goal = state["goal_amount"]
        remaining = max(0, goal - current)
        months_to_goal = _div_ceil(remaining, total_monthly) if total_monthly > 0 else 999
        return {
            "monthly_savings": monthly_savings,
            "expense_reduction": expense_reduction,
            "total_monthly": total_monthly,
            "total_annual": total_annual,
            "goal_amount": goal,
            "months_to_goal": months_to_goal,
        }

    elif code == "S-002":  # Spending Cut Impact
        dining = state["dining_out"]
        entertainment = state["entertainment"]
        shopping = state["shopping"]
        d_cut = slider_values["dining_cut_pct"]
        e_cut = slider_values["entertainment_cut_pct"]
        s_cut = slider_values["shopping_cut_pct"]
        monthly_saved = (
            dining * d_cut / 100
            + entertainment * e_cut / 100
            + shopping * s_cut / 100
        )
        annual_saved = monthly_saved * 12
        income = state["monthly_income"]
        old_rate = state["current_savings_rate"]
        new_rate = round(old_rate + (monthly_saved / income * 100), 1)
        return {
            "dining_cut_pct": d_cut,
            "entertainment_cut_pct": e_cut,
            "shopping_cut_pct": s_cut,
            "monthly_savings": round(monthly_saved, 2),
            "annual_savings": round(annual_saved, 2),
            "old_rate": old_rate,
            "new_rate": new_rate,
        }

    elif code == "S-003":  # Subscription Cancellation Planner
        subs = state["subscriptions"]
        cancel_count = min(slider_values["cancel_count"], len(subs))
        # Cancel most expensive first
        sorted_subs = sorted(subs, key=lambda s: s["monthly_cost"], reverse=True)
        cancelled = sorted_subs[:cancel_count]
        monthly_saved = sum(s["monthly_cost"] for s in cancelled)
        remaining = state["total_monthly"] - monthly_saved
        return {
            "cancel_count": cancel_count,
            "monthly_saved": round(monthly_saved, 2),
            "annual_saved": round(monthly_saved * 12, 2),
            "remaining": round(remaining, 2),
        }

    elif code == "S-004":  # Grocery Budget Optimizer
        weekly_grocery = state["weekly_grocery"]
        weekly_dining = state["weekly_dining"]
        waste_pct = state["food_waste_pct"]
        meal_prep = slider_values["meal_prep_days"]
        waste_red = slider_values["food_waste_reduction"]
        dining_red = slider_values["dining_reduction_pct"]
        # Meal prep saves ~$10/day prepped
        meal_savings = meal_prep * 10 * 4.33
        waste_savings = weekly_grocery * (waste_pct / 100) * (waste_red / 100) * 4.33
        dining_savings = weekly_dining * (dining_red / 100) * 4.33
        monthly = round(meal_savings + waste_savings + dining_savings, 2)
        return {
            "meal_prep_days": meal_prep,
            "food_waste_reduction": waste_red,
            "dining_reduction_pct": dining_red,
            "monthly_savings": monthly,
            "annual_savings": round(monthly * 12, 2),
        }

    elif code == "S-005":  # Debt Payoff Timeline
        debt = state["total_debt"]
        rate = state["avg_interest_rate"]
        minimum = state["minimum_payment"]
        extra = slider_values["extra_payment"]
        rate_red = slider_values["interest_rate_reduction"]
        eff_rate = max(0, rate - rate_red)
        payment = minimum + extra
        baseline_months, baseline_interest = _calc_payoff(debt, rate, minimum)
        months, total_interest = _calc_payoff(debt, eff_rate, payment)
        return {
            "extra_payment": extra,
            "interest_rate_reduction": rate_red,
            "months_to_payoff": months,
            "baseline_months": baseline_months,
            "total_interest": round(total_interest, 2),
            "interest_saved": round(baseline_interest - total_interest, 2),
        }

    elif code == "S-006":  # Snowball vs Avalanche
        extra = slider_values["extra_monthly"]
        strategy = slider_values["strategy"]
        debts = state["debts"]
        strategy_name = "snowball" if strategy == 0 else "avalanche"
        months, total_interest = _calc_multi_debt_payoff(debts, extra, strategy_name)
        alt_months, alt_interest = _calc_multi_debt_payoff(
            debts, extra, "avalanche" if strategy == 0 else "snowball"
        )
        diff = round(abs(total_interest - alt_interest), 2)
        comparison = (
            f"Avalanche saves ${diff} more in interest."
            if strategy == 0 and diff > 0
            else f"Snowball pays off first debt faster for motivation."
            if strategy == 1
            else "Both strategies produce similar results here."
        )
        return {
            "extra_monthly": extra,
            "strategy_name": strategy_name,
            "months": months,
            "total_interest": round(total_interest, 2),
            "comparison_note": comparison,
        }

    elif code == "S-007":  # Emergency Fund Builder
        current = state["current_fund"]
        expenses = state["monthly_expenses"]
        contrib = slider_values["monthly_contribution"]
        target_months = slider_values["target_months"]
        target_amount = expenses * target_months
        remaining = max(0, target_amount - current)
        months_to_goal = _div_ceil(remaining, contrib) if contrib > 0 else 999
        progress_pct = round(min(100, current / target_amount * 100), 1) if target_amount > 0 else 100
        return {
            "monthly_contribution": contrib,
            "target_months": target_months,
            "target_amount": target_amount,
            "months_to_goal": months_to_goal,
            "progress_pct": progress_pct,
        }

    elif code == "S-008":  # Emergency Expense Simulator
        emergency = slider_values["emergency_cost"]
        fund = slider_values["fund_level"]
        cc_rate = state["credit_card_rate"]
        shortfall = max(0, emergency - fund)
        if shortfall == 0:
            description = f"Your ${fund} fund fully covers the ${emergency} emergency. No debt needed."
        else:
            description = f"${shortfall} shortfall — would go on credit card at {cc_rate}% APR."
        # 12-month interest on shortfall
        cc_interest = round(shortfall * (cc_rate / 100) * 0.6, 2)  # ~60% of APR over 12mo with payments
        return {
            "emergency_cost": emergency,
            "fund_level": fund,
            "shortfall": shortfall,
            "outcome_description": description,
            "cc_interest_cost": cc_interest,
        }

    elif code == "S-009":  # Budget Rebalancer
        income = state["monthly_income"]
        housing = state["housing"]
        transport = state["transport"]
        utilities = state["utilities"]
        other = state["other"]
        food = slider_values["food_budget"]
        discretionary = slider_values["discretionary_budget"]
        savings = slider_values["savings_target"]
        total_expense = housing + food + transport + utilities + discretionary + other + savings
        balance = income - total_expense
        status = (
            f"Budget balanced with ${balance} remaining"
            if balance >= 0
            else f"Budget over by ${abs(balance)} — reduce spending or increase income"
        )
        savings_rate = round(savings / income * 100, 1) if income > 0 else 0
        return {
            "food_budget": food,
            "discretionary_budget": discretionary,
            "savings_target": savings,
            "balance_status": status,
            "annual_savings": savings * 12,
            "savings_rate": savings_rate,
        }

    elif code == "S-010":  # Income Allocation Planner
        extra = slider_values["extra_income"]
        save_pct = slider_values["savings_pct"]
        debt_pct = slider_values["debt_pct"]
        lifestyle_pct = max(0, 100 - save_pct - debt_pct)
        to_savings = round(extra * save_pct / 100, 2)
        to_debt = round(extra * debt_pct / 100, 2)
        to_lifestyle = round(extra * lifestyle_pct / 100, 2)
        debt = state["total_debt"]
        current_debt_payment = state["current_debt_payment"]
        new_payment = current_debt_payment + to_debt
        # Rough months saved estimation
        if to_debt > 0 and debt > 0:
            old_months = _div_ceil(debt, current_debt_payment) if current_debt_payment > 0 else 999
            new_months = _div_ceil(debt, new_payment) if new_payment > 0 else 999
            months_saved = max(0, old_months - new_months)
        else:
            months_saved = 0
        return {
            "extra_income": extra,
            "to_savings": to_savings,
            "to_debt": to_debt,
            "to_lifestyle": to_lifestyle,
            "annual_savings_impact": round(to_savings * 12, 2),
            "months_saved": months_saved,
        }

    # Default fallback
    return {"raw_sliders": slider_values, "note": "Outcome computed with defaults."}


def _generate_after_action_review(
    scenario: ScenarioDefinition, run: ScenarioRun
) -> dict:
    """Generate template-based After-Action Review."""
    outcome = run.computed_outcome or {}
    sliders = run.slider_values

    # Summary based on outcome
    summary_parts = []
    for key, value in outcome.items():
        if isinstance(value, (int, float)) and key not in ("strategy",):
            summary_parts.append(f"{key.replace('_', ' ')}: {value}")

    summary = f"In this '{scenario.title}' simulation, you explored: {', '.join(summary_parts[:5])}."

    # What worked: pick the slider with highest relative value
    what_worked = "Your chosen settings produced a reasonable outcome."
    if sliders:
        slider_defs = {s["key"]: s for s in scenario.sliders}
        for key, val in sliders.items():
            if key in slider_defs:
                sdef = slider_defs[key]
                if sdef["max"] > sdef["min"]:
                    pct = (val - sdef["min"]) / (sdef["max"] - sdef["min"])
                    if pct >= 0.5:
                        what_worked = f"Setting {sdef['label']} to {val} was an effective choice."
                        break

    # Improvement
    improvement = "Try adjusting sliders to more aggressive values to see if further gains are possible."

    return {
        "summary": summary,
        "what_worked": what_worked,
        "improvement": improvement,
        "learning_points": scenario.learning_points,
        "confidence": PRACTICE_CONFIDENCE_CAP,
    }


def _generate_plan_steps(
    scenario: ScenarioDefinition, run: ScenarioRun
) -> list[dict]:
    """Generate actionable plan steps from scenario outcome.

    Max 3 steps (matching coach plan mode constraint).
    """
    outcome = run.computed_outcome or {}
    steps = []

    # Step 1: Apply the key finding
    steps.append({
        "step_number": 1,
        "action": "apply_learning",
        "title": f"Apply insight from '{scenario.title}'",
        "description": (
            f"Based on your simulation, implement the changes you explored. "
            f"Confidence: {PRACTICE_CONFIDENCE_CAP} (practice-derived)."
        ),
        "source": "practice",
    })

    # Step 2: Specific action based on scenario category
    category_actions = {
        "save_money": {
            "title": "Set up automatic savings",
            "description": "Automate the savings amount you simulated to make it consistent.",
        },
        "reduce_spending": {
            "title": "Track spending for 1 week",
            "description": "Monitor your actual spending in the categories you simulated to validate your targets.",
        },
        "pay_off_debt": {
            "title": "Make your first extra payment",
            "description": "Apply the extra payment strategy from your simulation to your highest-priority debt.",
        },
        "build_emergency_fund": {
            "title": "Open or fund emergency account",
            "description": "Set up a high-yield savings account and make your first contribution.",
        },
        "budget_better": {
            "title": "Create your real budget",
            "description": "Use the allocations from your simulation as starting points for your actual budget.",
        },
    }
    cat_action = category_actions.get(
        scenario.category.value,
        {"title": "Take the first step", "description": "Act on what you learned."},
    )
    steps.append({
        "step_number": 2,
        "action": "category_specific",
        "title": cat_action["title"],
        "description": cat_action["description"],
        "source": "practice",
    })

    # Step 3: Validate with real data
    steps.append({
        "step_number": 3,
        "action": "validate_with_data",
        "title": "Compare with your real numbers",
        "description": (
            "Check your actual transactions and balances against the simulation. "
            "Real-data corroboration is needed to move from practice confidence to high confidence."
        ),
        "source": "practice",
    })

    return steps


def _div_ceil(a: int | float, b: int | float) -> int:
    """Integer ceiling division."""
    if b <= 0:
        return 999
    return int(-(-a // b))


def _calc_payoff(
    principal: float, annual_rate: float, monthly_payment: float
) -> tuple[int, float]:
    """Calculate months to payoff and total interest for a single debt."""
    if monthly_payment <= 0:
        return 999, 0
    balance = float(principal)
    monthly_rate = annual_rate / 100 / 12
    months = 0
    total_interest = 0.0
    while balance > 0 and months < 600:
        interest = balance * monthly_rate
        total_interest += interest
        payment = min(monthly_payment, balance + interest)
        balance = balance + interest - payment
        months += 1
        if balance < 0.01:
            break
    return months, total_interest


def _calc_multi_debt_payoff(
    debts: list[dict], extra_monthly: float, strategy: str
) -> tuple[int, float]:
    """Calculate multi-debt payoff using snowball or avalanche."""
    if not debts:
        return 0, 0

    # Copy debts
    remaining = [
        {"balance": float(d["balance"]), "rate": d["rate"], "minimum": d["minimum"]}
        for d in debts
    ]

    total_interest = 0.0
    months = 0

    while any(d["balance"] > 0.01 for d in remaining) and months < 600:
        months += 1
        extra_left = extra_monthly

        # Apply interest and minimum payments
        for d in remaining:
            if d["balance"] <= 0:
                continue
            interest = d["balance"] * d["rate"] / 100 / 12
            total_interest += interest
            d["balance"] += interest
            payment = min(d["minimum"], d["balance"])
            d["balance"] -= payment

        # Sort for strategy and apply extra
        active = [d for d in remaining if d["balance"] > 0.01]
        if not active:
            break

        if strategy == "snowball":
            active.sort(key=lambda d: d["balance"])
        else:  # avalanche
            active.sort(key=lambda d: d["rate"], reverse=True)

        for d in active:
            if extra_left <= 0:
                break
            payment = min(extra_left, d["balance"])
            d["balance"] -= payment
            extra_left -= payment

    return months, total_interest
