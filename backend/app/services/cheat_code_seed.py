"""Seed minimal cheat codes required to support First Win.

Only the minimal set per PRD — at least one quick_win (≤10 min).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeCategory, CheatCodeDefinition, CheatCodeDifficulty


SEED_CHEAT_CODES = [
    {
        "code": "CC-001",
        "title": "Cancel an Unused Subscription",
        "description": (
            "Review your recurring charges and cancel one subscription "
            "you no longer use or need."
        ),
        "category": CheatCodeCategory.save_money,
        "difficulty": CheatCodeDifficulty.quick_win,
        "estimated_minutes": 10,
        "steps": [
            {
                "step_number": 1,
                "title": "Review recurring charges",
                "description": "Look at your detected recurring patterns and identify subscriptions you no longer use.",
                "estimated_minutes": 3,
            },
            {
                "step_number": 2,
                "title": "Cancel the subscription",
                "description": "Log into the service and cancel or downgrade your plan.",
                "estimated_minutes": 5,
            },
            {
                "step_number": 3,
                "title": "Confirm cancellation",
                "description": "Verify you received a cancellation confirmation email.",
                "estimated_minutes": 2,
            },
        ],
        "potential_savings_min": "5.00",
        "potential_savings_max": "50.00",
    },
    {
        "code": "CC-002",
        "title": "Set a Weekly Dining Budget",
        "description": (
            "Based on your spending patterns, set a realistic weekly dining "
            "budget and track it for one week."
        ),
        "category": CheatCodeCategory.reduce_spending,
        "difficulty": CheatCodeDifficulty.easy,
        "estimated_minutes": 15,
        "steps": [
            {
                "step_number": 1,
                "title": "Review dining spending",
                "description": "Check your dining category spending over the past month.",
                "estimated_minutes": 3,
            },
            {
                "step_number": 2,
                "title": "Set a target budget",
                "description": "Choose a weekly dining budget that is 20% less than your current average.",
                "estimated_minutes": 5,
            },
            {
                "step_number": 3,
                "title": "Track for one week",
                "description": "Monitor your dining spending for 7 days against your target.",
                "estimated_minutes": 7,
            },
        ],
        "potential_savings_min": "20.00",
        "potential_savings_max": "100.00",
    },
    {
        "code": "CC-003",
        "title": "Start an Emergency Fund",
        "description": (
            "Open a savings account or designate funds for emergencies. "
            "Even $25 is a great start."
        ),
        "category": CheatCodeCategory.build_emergency_fund,
        "difficulty": CheatCodeDifficulty.easy,
        "estimated_minutes": 20,
        "steps": [
            {
                "step_number": 1,
                "title": "Choose a savings vehicle",
                "description": "Pick a high-yield savings account or set aside a separate fund.",
                "estimated_minutes": 10,
            },
            {
                "step_number": 2,
                "title": "Make a first deposit",
                "description": "Transfer at least $25 into your emergency fund.",
                "estimated_minutes": 5,
            },
            {
                "step_number": 3,
                "title": "Set up auto-transfer",
                "description": "Schedule a recurring weekly or monthly transfer to build the fund.",
                "estimated_minutes": 5,
            },
        ],
        "potential_savings_min": "25.00",
        "potential_savings_max": "500.00",
    },
    {
        "code": "CC-004",
        "title": "Negotiate a Lower Bill",
        "description": (
            "Call one of your service providers (internet, phone, insurance) "
            "and ask for a better rate."
        ),
        "category": CheatCodeCategory.save_money,
        "difficulty": CheatCodeDifficulty.medium,
        "estimated_minutes": 30,
        "steps": [
            {
                "step_number": 1,
                "title": "Pick a bill to negotiate",
                "description": "Choose the highest utility or service bill from your recurring charges.",
                "estimated_minutes": 3,
            },
            {
                "step_number": 2,
                "title": "Research competitor rates",
                "description": "Look up what competitors charge for similar service.",
                "estimated_minutes": 10,
            },
            {
                "step_number": 3,
                "title": "Call and negotiate",
                "description": "Call your provider, mention competitor rates, and ask for a discount or retention offer.",
                "estimated_minutes": 15,
            },
            {
                "step_number": 4,
                "title": "Confirm new rate",
                "description": "Verify the new rate on your next bill.",
                "estimated_minutes": 2,
            },
        ],
        "potential_savings_min": "10.00",
        "potential_savings_max": "80.00",
    },
    {
        "code": "CC-005",
        "title": "Review and Categorize Last Month's Spending",
        "description": (
            "Go through last month's transactions, ensure categories "
            "are correct, and identify your top 3 spending areas."
        ),
        "category": CheatCodeCategory.budget_better,
        "difficulty": CheatCodeDifficulty.quick_win,
        "estimated_minutes": 8,
        "steps": [
            {
                "step_number": 1,
                "title": "Review auto-categorized transactions",
                "description": "Check that your transactions are in the right categories.",
                "estimated_minutes": 4,
            },
            {
                "step_number": 2,
                "title": "Identify top spending areas",
                "description": "Note your top 3 categories by total spending.",
                "estimated_minutes": 4,
            },
        ],
        "potential_savings_min": None,
        "potential_savings_max": None,
    },
]


async def seed_cheat_codes(db: AsyncSession) -> list[CheatCodeDefinition]:
    """Seed the minimal cheat codes required for First Win.

    Idempotent: skips codes that already exist (by unique code field).
    Returns all seeded/existing definitions.
    """
    from decimal import Decimal

    results = []
    for data in SEED_CHEAT_CODES:
        existing = await db.execute(
            select(CheatCodeDefinition).where(
                CheatCodeDefinition.code == data["code"]
            )
        )
        existing_def = existing.scalar_one_or_none()
        if existing_def:
            results.append(existing_def)
            continue

        definition = CheatCodeDefinition(
            code=data["code"],
            title=data["title"],
            description=data["description"],
            category=data["category"],
            difficulty=data["difficulty"],
            estimated_minutes=data["estimated_minutes"],
            steps=data["steps"],
            potential_savings_min=(
                Decimal(data["potential_savings_min"])
                if data["potential_savings_min"]
                else None
            ),
            potential_savings_max=(
                Decimal(data["potential_savings_max"])
                if data["potential_savings_max"]
                else None
            ),
        )
        db.add(definition)
        results.append(definition)

    await db.flush()
    return results
