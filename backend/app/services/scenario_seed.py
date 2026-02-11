"""Seed data: 10 practice scenarios with simulator sliders across 5 categories."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.practice import ScenarioCategory, ScenarioDefinition

SCENARIOS = [
    # --- save_money (2) ---
    {
        "code": "S-001",
        "title": "Savings Rate Simulator",
        "description": "Adjust your monthly savings rate to see how it affects your 12-month savings goal.",
        "category": ScenarioCategory.save_money,
        "estimated_minutes": 5,
        "display_order": 1,
        "initial_state": {
            "monthly_income": 4000,
            "monthly_expenses": 3200,
            "current_savings": 500,
            "goal_amount": 5000,
        },
        "sliders": [
            {"key": "monthly_savings", "label": "Monthly Savings ($)", "min": 50, "max": 800, "step": 50, "default": 200},
            {"key": "expense_reduction", "label": "Expense Reduction ($)", "min": 0, "max": 500, "step": 25, "default": 0},
        ],
        "outcome_template": (
            "With ${monthly_savings}/month savings and ${expense_reduction} expense reduction, "
            "you'd save ${total_annual} in 12 months. "
            "You'd reach your ${goal_amount} goal in {months_to_goal} months. "
            "Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Even small increases in savings rate compound significantly over time.",
            "Combining savings with expense reduction accelerates goal achievement.",
            "Consistency matters more than the exact amount.",
        ],
    },
    {
        "code": "S-002",
        "title": "Spending Cut Impact",
        "description": "See how cutting discretionary spending affects your annual savings.",
        "category": ScenarioCategory.save_money,
        "estimated_minutes": 5,
        "display_order": 2,
        "initial_state": {
            "monthly_income": 4000,
            "dining_out": 400,
            "entertainment": 200,
            "shopping": 300,
            "current_savings_rate": 10,
        },
        "sliders": [
            {"key": "dining_cut_pct", "label": "Dining Reduction (%)", "min": 0, "max": 80, "step": 10, "default": 30},
            {"key": "entertainment_cut_pct", "label": "Entertainment Reduction (%)", "min": 0, "max": 80, "step": 10, "default": 20},
            {"key": "shopping_cut_pct", "label": "Shopping Reduction (%)", "min": 0, "max": 80, "step": 10, "default": 25},
        ],
        "outcome_template": (
            "By cutting dining {dining_cut_pct}%, entertainment {entertainment_cut_pct}%, "
            "and shopping {shopping_cut_pct}%, you'd save ${monthly_savings}/month "
            "(${annual_savings}/year). Your savings rate would increase from "
            "{old_rate}% to {new_rate}%. Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Dining out is typically the largest discretionary expense.",
            "Percentage cuts are more sustainable than zero-spending goals.",
            "Track actual spending for 1 month before setting targets.",
        ],
    },
    # --- reduce_spending (2) ---
    {
        "code": "S-003",
        "title": "Subscription Cancellation Planner",
        "description": "Select subscriptions to cancel and see your monthly/annual savings.",
        "category": ScenarioCategory.reduce_spending,
        "estimated_minutes": 5,
        "display_order": 3,
        "initial_state": {
            "subscriptions": [
                {"name": "Streaming A", "monthly_cost": 15.99},
                {"name": "Streaming B", "monthly_cost": 12.99},
                {"name": "Music Service", "monthly_cost": 10.99},
                {"name": "Cloud Storage", "monthly_cost": 2.99},
                {"name": "News", "monthly_cost": 9.99},
                {"name": "Gym", "monthly_cost": 49.99},
            ],
            "total_monthly": 102.95,
        },
        "sliders": [
            {"key": "cancel_count", "label": "Subscriptions to Cancel", "min": 0, "max": 6, "step": 1, "default": 2},
        ],
        "outcome_template": (
            "Cancelling {cancel_count} subscription(s) saves ~${monthly_saved}/month "
            "(${annual_saved}/year). Your remaining subscription cost: "
            "${remaining}/month. Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Start by cancelling services unused in the past 30 days.",
            "Even 2-3 cancelled subscriptions can save $300-600/year.",
            "Re-evaluate subscriptions quarterly.",
        ],
    },
    {
        "code": "S-004",
        "title": "Grocery Budget Optimizer",
        "description": "Adjust grocery habits to find savings without sacrificing nutrition.",
        "category": ScenarioCategory.reduce_spending,
        "estimated_minutes": 5,
        "display_order": 4,
        "initial_state": {
            "weekly_grocery": 150,
            "weekly_dining": 100,
            "meal_prep_days": 0,
            "food_waste_pct": 20,
        },
        "sliders": [
            {"key": "meal_prep_days", "label": "Meal Prep Days/Week", "min": 0, "max": 5, "step": 1, "default": 2},
            {"key": "food_waste_reduction", "label": "Food Waste Reduction (%)", "min": 0, "max": 80, "step": 10, "default": 40},
            {"key": "dining_reduction_pct", "label": "Dining Out Reduction (%)", "min": 0, "max": 80, "step": 10, "default": 30},
        ],
        "outcome_template": (
            "With {meal_prep_days} meal prep days, {food_waste_reduction}% less food waste, "
            "and {dining_reduction_pct}% less dining out, you'd save ${monthly_savings}/month "
            "(${annual_savings}/year). Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Meal prepping 2-3 days/week saves the average household $200-300/month.",
            "Reducing food waste saves money and resources.",
            "Gradual changes stick better than extreme cuts.",
        ],
    },
    # --- pay_off_debt (2) ---
    {
        "code": "S-005",
        "title": "Debt Payoff Timeline",
        "description": "Adjust extra monthly payments to see how fast you can become debt-free.",
        "category": ScenarioCategory.pay_off_debt,
        "estimated_minutes": 6,
        "display_order": 5,
        "initial_state": {
            "total_debt": 15000,
            "avg_interest_rate": 18.0,
            "minimum_payment": 300,
            "monthly_income": 4000,
        },
        "sliders": [
            {"key": "extra_payment", "label": "Extra Monthly Payment ($)", "min": 0, "max": 500, "step": 25, "default": 100},
            {"key": "interest_rate_reduction", "label": "Rate Reduction (% pts)", "min": 0, "max": 10, "step": 1, "default": 0},
        ],
        "outcome_template": (
            "With ${extra_payment}/month extra and {interest_rate_reduction}% rate reduction, "
            "you'd be debt-free in {months_to_payoff} months (vs. {baseline_months} months "
            "with minimums only). Total interest: ${total_interest} (saves ${interest_saved}). "
            "Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Extra payments attack principal directly, reducing future interest.",
            "Negotiating a lower rate or balance transfer can save thousands.",
            "Even $50 extra/month significantly shortens the payoff timeline.",
        ],
    },
    {
        "code": "S-006",
        "title": "Snowball vs. Avalanche Calculator",
        "description": "Compare debt payoff strategies with your actual debt balances.",
        "category": ScenarioCategory.pay_off_debt,
        "estimated_minutes": 6,
        "display_order": 6,
        "initial_state": {
            "debts": [
                {"name": "Credit Card A", "balance": 3000, "rate": 22.0, "minimum": 75},
                {"name": "Credit Card B", "balance": 5000, "rate": 18.0, "minimum": 100},
                {"name": "Personal Loan", "balance": 7000, "rate": 12.0, "minimum": 150},
            ],
            "total_debt": 15000,
        },
        "sliders": [
            {"key": "extra_monthly", "label": "Extra Monthly Budget ($)", "min": 0, "max": 500, "step": 25, "default": 150},
            {"key": "strategy", "label": "Strategy (0=Snowball, 1=Avalanche)", "min": 0, "max": 1, "step": 1, "default": 0},
        ],
        "outcome_template": (
            "Using the {strategy_name} method with ${extra_monthly}/month extra, "
            "you'd be debt-free in {months} months. Total interest paid: ${total_interest}. "
            "{comparison_note} Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Avalanche saves more on interest; snowball provides quicker wins.",
            "The best strategy is the one you'll stick with.",
            "Both are far better than minimum payments only.",
        ],
    },
    # --- build_emergency_fund (2) ---
    {
        "code": "S-007",
        "title": "Emergency Fund Builder",
        "description": "Plan your path to a fully-funded emergency fund.",
        "category": ScenarioCategory.build_emergency_fund,
        "estimated_minutes": 5,
        "display_order": 7,
        "initial_state": {
            "monthly_expenses": 3000,
            "current_fund": 500,
            "target_months": 3,
            "monthly_income": 4000,
        },
        "sliders": [
            {"key": "monthly_contribution", "label": "Monthly Contribution ($)", "min": 50, "max": 600, "step": 25, "default": 200},
            {"key": "target_months", "label": "Target Months of Expenses", "min": 1, "max": 6, "step": 1, "default": 3},
        ],
        "outcome_template": (
            "Saving ${monthly_contribution}/month toward a {target_months}-month fund "
            "(${target_amount}), you'd be fully funded in {months_to_goal} months. "
            "Current progress: {progress_pct}%. Confidence: medium (simulated)."
        ),
        "learning_points": [
            "$1,000 covers most common emergencies (car repair, medical copay).",
            "3 months of expenses provides a solid safety net.",
            "High-yield savings accounts maximize your emergency fund growth.",
        ],
    },
    {
        "code": "S-008",
        "title": "Emergency Expense Simulator",
        "description": "See how your finances handle unexpected expenses with different fund levels.",
        "category": ScenarioCategory.build_emergency_fund,
        "estimated_minutes": 5,
        "display_order": 8,
        "initial_state": {
            "monthly_income": 4000,
            "monthly_expenses": 3200,
            "emergency_fund": 1000,
            "credit_card_rate": 20.0,
        },
        "sliders": [
            {"key": "emergency_cost", "label": "Emergency Cost ($)", "min": 500, "max": 5000, "step": 250, "default": 1500},
            {"key": "fund_level", "label": "Emergency Fund Level ($)", "min": 0, "max": 10000, "step": 500, "default": 1000},
        ],
        "outcome_template": (
            "A ${emergency_cost} emergency with a ${fund_level} fund: "
            "{outcome_description} "
            "Credit card cost if borrowed: ${cc_interest_cost} in interest over 12 months. "
            "Confidence: medium (simulated)."
        ),
        "learning_points": [
            "Without an emergency fund, unexpected costs become high-interest debt.",
            "A $1,000 fund covers 60% of common emergencies without debt.",
            "The cost of NOT having an emergency fund is measurable in interest paid.",
        ],
    },
    # --- budget_better (2) ---
    {
        "code": "S-009",
        "title": "Budget Rebalancer",
        "description": "Adjust your budget allocation and see the impact on savings and lifestyle.",
        "category": ScenarioCategory.budget_better,
        "estimated_minutes": 6,
        "display_order": 9,
        "initial_state": {
            "monthly_income": 4000,
            "housing": 1200,
            "food": 600,
            "transport": 400,
            "utilities": 200,
            "discretionary": 800,
            "savings": 400,
            "other": 400,
        },
        "sliders": [
            {"key": "food_budget", "label": "Food Budget ($)", "min": 200, "max": 800, "step": 25, "default": 600},
            {"key": "discretionary_budget", "label": "Discretionary ($)", "min": 200, "max": 1000, "step": 25, "default": 800},
            {"key": "savings_target", "label": "Savings Target ($)", "min": 100, "max": 1000, "step": 25, "default": 400},
        ],
        "outcome_template": (
            "With food at ${food_budget}, discretionary at ${discretionary_budget}, "
            "and savings at ${savings_target}: {balance_status}. "
            "Annual savings: ${annual_savings}. Savings rate: {savings_rate}%. "
            "Confidence: medium (simulated)."
        ),
        "learning_points": [
            "A balanced budget doesn't mean equal categories — priorities vary.",
            "Savings rate is the single most important financial metric.",
            "Review and adjust your budget monthly until it stabilizes.",
        ],
    },
    {
        "code": "S-010",
        "title": "Income Allocation Planner",
        "description": "Plan how to allocate a raise, bonus, or side income for maximum impact.",
        "category": ScenarioCategory.budget_better,
        "estimated_minutes": 5,
        "display_order": 10,
        "initial_state": {
            "current_monthly_income": 4000,
            "current_savings": 400,
            "current_debt_payment": 300,
            "total_debt": 10000,
        },
        "sliders": [
            {"key": "extra_income", "label": "Extra Monthly Income ($)", "min": 100, "max": 2000, "step": 100, "default": 500},
            {"key": "savings_pct", "label": "% to Savings", "min": 0, "max": 100, "step": 10, "default": 50},
            {"key": "debt_pct", "label": "% to Debt", "min": 0, "max": 100, "step": 10, "default": 30},
        ],
        "outcome_template": (
            "With ${extra_income}/month extra: ${to_savings}/month to savings, "
            "${to_debt}/month to debt, ${to_lifestyle}/month to lifestyle. "
            "Annual savings impact: +${annual_savings_impact}. "
            "Debt payoff accelerated by {months_saved} months. "
            "Confidence: medium (simulated)."
        ),
        "learning_points": [
            "The 50/30/20 rule applies to raises too — save at least 50%.",
            "Lifestyle inflation erodes raises if not managed deliberately.",
            "Allocating to both savings and debt creates dual momentum.",
        ],
    },
]


async def seed_scenarios(db: AsyncSession) -> int:
    """Seed scenario definitions. Idempotent — skips existing codes.

    Returns count of newly created scenarios.
    """
    created = 0
    for scenario_data in SCENARIOS:
        result = await db.execute(
            select(ScenarioDefinition).where(
                ScenarioDefinition.code == scenario_data["code"]
            )
        )
        if result.scalar_one_or_none() is not None:
            continue

        scenario = ScenarioDefinition(
            code=scenario_data["code"],
            title=scenario_data["title"],
            description=scenario_data["description"],
            category=scenario_data["category"],
            initial_state=scenario_data["initial_state"],
            sliders=scenario_data["sliders"],
            outcome_template=scenario_data["outcome_template"],
            learning_points=scenario_data["learning_points"],
            estimated_minutes=scenario_data["estimated_minutes"],
            display_order=scenario_data["display_order"],
        )
        db.add(scenario)
        created += 1

    await db.flush()
    return created
