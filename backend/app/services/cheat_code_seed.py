"""Seed cheat code definitions library.

Phase 2: 5 minimal codes. Phase 3: expanded to ≥25.
All codes are actionable, no automation of money movement.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cheat_code import CheatCodeCategory, CheatCodeDefinition, CheatCodeDifficulty

# ─── Categories shorthand ───
_SAVE = CheatCodeCategory.save_money
_REDUCE = CheatCodeCategory.reduce_spending
_DEBT = CheatCodeCategory.pay_off_debt
_EMERGENCY = CheatCodeCategory.build_emergency_fund
_BUDGET = CheatCodeCategory.budget_better

# ─── Difficulty shorthand ───
_QW = CheatCodeDifficulty.quick_win
_EASY = CheatCodeDifficulty.easy
_MED = CheatCodeDifficulty.medium
_INV = CheatCodeDifficulty.involved

SEED_CHEAT_CODES = [
    # ═══════════════════════════════════════════
    # CC-001 through CC-005: Phase 2 originals
    # ═══════════════════════════════════════════
    {
        "code": "CC-001",
        "title": "Cancel an Unused Subscription",
        "description": (
            "Review your recurring charges and cancel one subscription "
            "you no longer use or need."
        ),
        "category": _SAVE,
        "difficulty": _QW,
        "estimated_minutes": 10,
        "steps": [
            {"step_number": 1, "title": "Review recurring charges",
             "description": "Look at your detected recurring patterns and identify subscriptions you no longer use.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Cancel the subscription",
             "description": "Log into the service and cancel or downgrade your plan.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Confirm cancellation",
             "description": "Verify you received a cancellation confirmation email.",
             "estimated_minutes": 2},
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
        "category": _REDUCE,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "Review dining spending",
             "description": "Check your dining category spending over the past month.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Set a target budget",
             "description": "Choose a weekly dining budget that is 20% less than your current average.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Track for one week",
             "description": "Monitor your dining spending for 7 days against your target.",
             "estimated_minutes": 7},
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
        "category": _EMERGENCY,
        "difficulty": _EASY,
        "estimated_minutes": 20,
        "steps": [
            {"step_number": 1, "title": "Choose a savings vehicle",
             "description": "Pick a high-yield savings account or set aside a separate fund.",
             "estimated_minutes": 10},
            {"step_number": 2, "title": "Make a first deposit",
             "description": "Transfer at least $25 into your emergency fund.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Set up auto-transfer",
             "description": "Schedule a recurring weekly or monthly transfer to build the fund.",
             "estimated_minutes": 5},
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
        "category": _SAVE,
        "difficulty": _MED,
        "estimated_minutes": 30,
        "steps": [
            {"step_number": 1, "title": "Pick a bill to negotiate",
             "description": "Choose the highest utility or service bill from your recurring charges.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Research competitor rates",
             "description": "Look up what competitors charge for similar service.",
             "estimated_minutes": 10},
            {"step_number": 3, "title": "Call and negotiate",
             "description": "Call your provider, mention competitor rates, and ask for a discount or retention offer.",
             "estimated_minutes": 15},
            {"step_number": 4, "title": "Confirm new rate",
             "description": "Verify the new rate on your next bill.",
             "estimated_minutes": 2},
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
        "category": _BUDGET,
        "difficulty": _QW,
        "estimated_minutes": 8,
        "steps": [
            {"step_number": 1, "title": "Review auto-categorized transactions",
             "description": "Check that your transactions are in the right categories.",
             "estimated_minutes": 4},
            {"step_number": 2, "title": "Identify top spending areas",
             "description": "Note your top 3 categories by total spending.",
             "estimated_minutes": 4},
        ],
        "potential_savings_min": None,
        "potential_savings_max": None,
    },
    # ═══════════════════════════════════════════
    # CC-006 through CC-025: Phase 3 expansion
    # ═══════════════════════════════════════════
    {
        "code": "CC-006",
        "title": "Downgrade a Subscription Tier",
        "description": "Switch from a premium to a basic tier on a service you use infrequently.",
        "category": _SAVE,
        "difficulty": _QW,
        "estimated_minutes": 8,
        "steps": [
            {"step_number": 1, "title": "Identify over-tiered subscriptions",
             "description": "Find services where you pay for premium but use basic features.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Downgrade the plan",
             "description": "Log in and switch to a lower-cost tier.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "3.00",
        "potential_savings_max": "30.00",
    },
    {
        "code": "CC-007",
        "title": "Switch to a No-Fee Bank Account",
        "description": "If you are paying monthly bank fees, research and switch to a fee-free alternative.",
        "category": _SAVE,
        "difficulty": _MED,
        "estimated_minutes": 45,
        "steps": [
            {"step_number": 1, "title": "Check for current fees",
             "description": "Review your bank statements for monthly maintenance or ATM fees.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Research alternatives",
             "description": "Compare no-fee checking accounts from online banks and credit unions.",
             "estimated_minutes": 15},
            {"step_number": 3, "title": "Open the new account",
             "description": "Apply for the no-fee account online.",
             "estimated_minutes": 15},
            {"step_number": 4, "title": "Redirect deposits",
             "description": "Update your direct deposit and recurring payments to the new account.",
             "estimated_minutes": 10},
        ],
        "potential_savings_min": "5.00",
        "potential_savings_max": "25.00",
    },
    {
        "code": "CC-008",
        "title": "Set Up a No-Spend Day",
        "description": "Pick one day this week where you spend $0. Prep meals, pack lunch, skip impulse buys.",
        "category": _REDUCE,
        "difficulty": _QW,
        "estimated_minutes": 5,
        "steps": [
            {"step_number": 1, "title": "Pick your no-spend day",
             "description": "Choose a day this week that works best for zero discretionary spending.",
             "estimated_minutes": 2},
            {"step_number": 2, "title": "Prep for the day",
             "description": "Plan meals from what you already have. Remove payment apps from your home screen.",
             "estimated_minutes": 3},
        ],
        "potential_savings_min": "10.00",
        "potential_savings_max": "40.00",
    },
    {
        "code": "CC-009",
        "title": "Audit Your Grocery Spending",
        "description": "Review last month's grocery receipts, identify waste, and plan a more efficient shopping list.",
        "category": _REDUCE,
        "difficulty": _EASY,
        "estimated_minutes": 20,
        "steps": [
            {"step_number": 1, "title": "Tally grocery spend",
             "description": "Sum up your grocery transactions from last month.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Identify waste patterns",
             "description": "Note items you regularly buy but don't finish or use.",
             "estimated_minutes": 10},
            {"step_number": 3, "title": "Create an efficient list",
             "description": "Write a focused shopping list for next week based on what you actually eat.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "15.00",
        "potential_savings_max": "75.00",
    },
    {
        "code": "CC-010",
        "title": "Set Up the 24-Hour Rule",
        "description": "Before any non-essential purchase over $25, wait 24 hours. Track what you don't buy.",
        "category": _REDUCE,
        "difficulty": _QW,
        "estimated_minutes": 5,
        "steps": [
            {"step_number": 1, "title": "Set your threshold",
             "description": "Decide on your impulse-buy threshold (e.g. $25).",
             "estimated_minutes": 2},
            {"step_number": 2, "title": "Create a waiting list",
             "description": "Start a note or list where you record items you want to buy. Wait 24 hours before purchasing.",
             "estimated_minutes": 3},
        ],
        "potential_savings_min": "25.00",
        "potential_savings_max": "150.00",
    },
    {
        "code": "CC-011",
        "title": "Unsubscribe from Marketing Emails",
        "description": "Unsubscribe from 10+ retail marketing emails to reduce impulse purchase triggers.",
        "category": _REDUCE,
        "difficulty": _QW,
        "estimated_minutes": 10,
        "steps": [
            {"step_number": 1, "title": "Search promotional emails",
             "description": "Search your inbox for 'unsubscribe' and identify retail marketing senders.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Unsubscribe from 10+",
             "description": "Click unsubscribe on at least 10 retail marketing email lists.",
             "estimated_minutes": 7},
        ],
        "potential_savings_min": "10.00",
        "potential_savings_max": "100.00",
    },
    {
        "code": "CC-012",
        "title": "List All Monthly Subscriptions",
        "description": "Create a complete inventory of every recurring charge — streaming, apps, memberships, software.",
        "category": _BUDGET,
        "difficulty": _QW,
        "estimated_minutes": 10,
        "steps": [
            {"step_number": 1, "title": "Review recurring patterns",
             "description": "Check your detected recurring charges in the app.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Check for hidden charges",
             "description": "Search bank statements for annual or quarterly subscriptions not yet detected.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Note total monthly cost",
             "description": "Sum all subscriptions to see your total monthly subscription spend.",
             "estimated_minutes": 2},
        ],
        "potential_savings_min": None,
        "potential_savings_max": None,
    },
    {
        "code": "CC-013",
        "title": "Create a Simple Monthly Budget",
        "description": "Using your actual spending data, create a realistic monthly budget with 3-5 categories.",
        "category": _BUDGET,
        "difficulty": _EASY,
        "estimated_minutes": 25,
        "steps": [
            {"step_number": 1, "title": "Review monthly income",
             "description": "Confirm your total take-home pay from last month.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Identify fixed expenses",
             "description": "List rent, utilities, insurance, and other non-negotiable expenses.",
             "estimated_minutes": 7},
            {"step_number": 3, "title": "Set variable category limits",
             "description": "Based on your spending data, set limits for dining, shopping, entertainment.",
             "estimated_minutes": 10},
            {"step_number": 4, "title": "Calculate remaining savings",
             "description": "Income minus expenses = your target monthly savings.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "50.00",
        "potential_savings_max": "300.00",
    },
    {
        "code": "CC-014",
        "title": "Calculate Your Net Worth",
        "description": "Add up all assets and subtract all debts to get your current net worth snapshot.",
        "category": _BUDGET,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "List all assets",
             "description": "Include bank accounts, investments, property value, and valuables.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "List all debts",
             "description": "Include credit cards, student loans, car loans, mortgage, and any other debts.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Calculate net worth",
             "description": "Assets minus debts = net worth. Record this as your baseline.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": None,
        "potential_savings_max": None,
    },
    {
        "code": "CC-015",
        "title": "Pay Off Your Smallest Debt First",
        "description": "Identify your smallest debt balance and make an extra payment toward it this month.",
        "category": _DEBT,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "List all debts by balance",
             "description": "Order your debts from smallest to largest balance.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Find extra money",
             "description": "Identify $25-100 from your budget or savings from other cheat codes.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Make the extra payment",
             "description": "Apply the extra amount to your smallest debt balance.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "5.00",
        "potential_savings_max": "50.00",
    },
    {
        "code": "CC-016",
        "title": "Check Your Credit Card Interest Rates",
        "description": "Review interest rates on all credit cards and identify which ones cost you the most.",
        "category": _DEBT,
        "difficulty": _QW,
        "estimated_minutes": 8,
        "steps": [
            {"step_number": 1, "title": "Gather card statements",
             "description": "Check the APR on each credit card you carry a balance on.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Rank by interest cost",
             "description": "Note which card costs you the most in monthly interest charges.",
             "estimated_minutes": 3},
        ],
        "potential_savings_min": None,
        "potential_savings_max": None,
    },
    {
        "code": "CC-017",
        "title": "Request a Credit Card Rate Reduction",
        "description": "Call your highest-APR credit card and ask for a lower interest rate.",
        "category": _DEBT,
        "difficulty": _MED,
        "estimated_minutes": 20,
        "steps": [
            {"step_number": 1, "title": "Prepare your case",
             "description": "Note your payment history, credit score, and competing offers.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Call the issuer",
             "description": "Call the number on the back of your card and ask for the retention department.",
             "estimated_minutes": 10},
            {"step_number": 3, "title": "Record the result",
             "description": "Note the new rate or reason for denial. Try again in 3-6 months if denied.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "10.00",
        "potential_savings_max": "100.00",
    },
    {
        "code": "CC-018",
        "title": "Set Up Automatic Debt Payments",
        "description": "Configure autopay for at least the minimum on all debts to avoid late fees.",
        "category": _DEBT,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "List debts without autopay",
             "description": "Identify which debts you are paying manually each month.",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Set up autopay",
             "description": "Configure automatic minimum payments through each lender's website.",
             "estimated_minutes": 10},
            {"step_number": 3, "title": "Verify setup",
             "description": "Confirm each autopay is active and check the payment dates.",
             "estimated_minutes": 2},
        ],
        "potential_savings_min": "25.00",
        "potential_savings_max": "75.00",
    },
    {
        "code": "CC-019",
        "title": "Set a Savings Goal with a Deadline",
        "description": "Pick a specific savings target and date, then calculate the monthly amount needed.",
        "category": _EMERGENCY,
        "difficulty": _QW,
        "estimated_minutes": 8,
        "steps": [
            {"step_number": 1, "title": "Define the goal",
             "description": "Choose a specific amount and target date (e.g. $500 by end of quarter).",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Calculate monthly savings",
             "description": "Divide the target by the number of months remaining.",
             "estimated_minutes": 2},
            {"step_number": 3, "title": "Record the goal",
             "description": "Add this as a goal in the app with the target amount and date.",
             "estimated_minutes": 3},
        ],
        "potential_savings_min": "50.00",
        "potential_savings_max": "500.00",
    },
    {
        "code": "CC-020",
        "title": "Find One Free Alternative",
        "description": "Identify one paid service or activity and replace it with a free alternative for one month.",
        "category": _SAVE,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "Pick a paid service",
             "description": "Choose a subscription or recurring expense that has free alternatives (e.g. gym, streaming, software).",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Find the free alternative",
             "description": "Research and sign up for a free option (e.g. YouTube instead of premium streaming, outdoor exercise instead of gym).",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Try it for one month",
             "description": "Use the free alternative exclusively for 30 days and track satisfaction.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "10.00",
        "potential_savings_max": "60.00",
    },
    {
        "code": "CC-021",
        "title": "Reduce Utility Costs",
        "description": "Review utility bills and implement one energy-saving change to lower costs.",
        "category": _SAVE,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "Review utility bills",
             "description": "Check your last 3 months of electric, gas, and water bills for trends.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Implement one change",
             "description": "Pick one action: adjust thermostat by 2°F, switch to LED bulbs, or reduce hot water usage.",
             "estimated_minutes": 5},
            {"step_number": 3, "title": "Track the result",
             "description": "Compare next month's bill to see if the change made a difference.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "5.00",
        "potential_savings_max": "40.00",
    },
    {
        "code": "CC-022",
        "title": "Pack Lunch for a Week",
        "description": "Replace bought lunches with packed lunches for 5 work days. Track the savings.",
        "category": _REDUCE,
        "difficulty": _EASY,
        "estimated_minutes": 20,
        "steps": [
            {"step_number": 1, "title": "Calculate current lunch spend",
             "description": "Review your recent weekday dining/food transactions to find your average daily lunch cost.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Plan 5 packed lunches",
             "description": "Choose simple, affordable lunch options and shop for ingredients.",
             "estimated_minutes": 10},
            {"step_number": 3, "title": "Track savings",
             "description": "At the end of the week, compare your packed lunch grocery cost to your normal lunch spend.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "25.00",
        "potential_savings_max": "75.00",
    },
    {
        "code": "CC-023",
        "title": "Review Insurance Policies",
        "description": "Compare your auto, renter's, or health insurance to alternatives for better rates.",
        "category": _SAVE,
        "difficulty": _INV,
        "estimated_minutes": 60,
        "steps": [
            {"step_number": 1, "title": "Gather current policies",
             "description": "Note your current coverage levels, deductibles, and premiums.",
             "estimated_minutes": 10},
            {"step_number": 2, "title": "Get comparison quotes",
             "description": "Use a comparison site or call 2-3 competing insurers for quotes.",
             "estimated_minutes": 30},
            {"step_number": 3, "title": "Evaluate options",
             "description": "Compare coverage and price. Consider bundling discounts.",
             "estimated_minutes": 15},
            {"step_number": 4, "title": "Switch if beneficial",
             "description": "If you find savings of $10+/month with equal coverage, make the switch.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "15.00",
        "potential_savings_max": "150.00",
    },
    {
        "code": "CC-024",
        "title": "Set Up a Sinking Fund",
        "description": "Identify a known future expense (car repair, holiday gifts) and start saving for it monthly.",
        "category": _EMERGENCY,
        "difficulty": _EASY,
        "estimated_minutes": 15,
        "steps": [
            {"step_number": 1, "title": "Identify a future expense",
             "description": "Pick a predictable expense coming in 3-12 months (e.g. car registration, holiday gifts, annual subscription).",
             "estimated_minutes": 3},
            {"step_number": 2, "title": "Calculate monthly amount",
             "description": "Divide the expected cost by months remaining.",
             "estimated_minutes": 2},
            {"step_number": 3, "title": "Start saving",
             "description": "Set aside the monthly amount in a separate fund or envelope.",
             "estimated_minutes": 5},
            {"step_number": 4, "title": "Add as a goal",
             "description": "Record this sinking fund as a goal in the app.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "20.00",
        "potential_savings_max": "200.00",
    },
    {
        "code": "CC-025",
        "title": "Check for Duplicate Charges",
        "description": "Scan recent transactions for duplicate or erroneous charges and dispute them.",
        "category": _SAVE,
        "difficulty": _QW,
        "estimated_minutes": 10,
        "steps": [
            {"step_number": 1, "title": "Scan for duplicates",
             "description": "Look through your transactions for charges that appear twice on the same day or from the same merchant.",
             "estimated_minutes": 5},
            {"step_number": 2, "title": "Dispute if found",
             "description": "Contact your bank or the merchant to dispute any duplicate or erroneous charges.",
             "estimated_minutes": 5},
        ],
        "potential_savings_min": "5.00",
        "potential_savings_max": "100.00",
    },
]


async def seed_cheat_codes(db: AsyncSession) -> list[CheatCodeDefinition]:
    """Seed the cheat code definitions library.

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
