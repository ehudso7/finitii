"""Seed data: 10 lessons across 5 financial categories (2 per category)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learn import LessonCategory, LessonDefinition

LESSONS = [
    # --- save_money (2) ---
    {
        "code": "L-001",
        "title": "The 50/30/20 Budget Rule",
        "description": "Learn the foundational budgeting framework: 50% needs, 30% wants, 20% savings.",
        "category": LessonCategory.save_money,
        "estimated_minutes": 8,
        "display_order": 1,
        "sections": [
            {
                "section_number": 1,
                "title": "What is 50/30/20?",
                "content": "The 50/30/20 rule divides your after-tax income into three categories: 50% for needs (rent, groceries, utilities), 30% for wants (dining, entertainment, shopping), and 20% for savings and debt repayment. This framework gives you a simple starting point for managing money.",
                "key_takeaway": "Allocate 50% needs, 30% wants, 20% savings.",
            },
            {
                "section_number": 2,
                "title": "Applying the Rule",
                "content": "Calculate your after-tax monthly income. Multiply by 0.5, 0.3, and 0.2 to find your target amounts for each category. Compare these targets to your actual spending to identify where you're over or under budget.",
                "key_takeaway": "Compare your actual spending against the 50/30/20 targets.",
            },
            {
                "section_number": 3,
                "title": "When to Adjust",
                "content": "In high cost-of-living areas, needs may exceed 50%. Adjust the ratios but always prioritize savings. Even 10% savings is better than 0%. The key is consistency, not perfection.",
                "key_takeaway": "Adjust ratios to your situation but always save something.",
            },
        ],
    },
    {
        "code": "L-002",
        "title": "Automating Your Savings",
        "description": "Set up automatic transfers to make saving effortless and consistent.",
        "category": LessonCategory.save_money,
        "estimated_minutes": 6,
        "display_order": 2,
        "sections": [
            {
                "section_number": 1,
                "title": "Pay Yourself First",
                "content": "The most effective savings strategy is to transfer money to savings before spending on anything else. Set up an automatic transfer on payday so savings happens without willpower.",
                "key_takeaway": "Automate savings on payday before other spending.",
            },
            {
                "section_number": 2,
                "title": "Choosing the Right Amount",
                "content": "Start with what you can afford — even $25/month builds the habit. Increase by $25 every month as you adjust. The compound effect of small, consistent savings is powerful over time.",
                "key_takeaway": "Start small and increase gradually.",
            },
        ],
    },
    # --- reduce_spending (2) ---
    {
        "code": "L-003",
        "title": "Subscription Audit",
        "description": "Identify and eliminate unused subscriptions that quietly drain your budget.",
        "category": LessonCategory.reduce_spending,
        "estimated_minutes": 7,
        "display_order": 3,
        "sections": [
            {
                "section_number": 1,
                "title": "The Subscription Trap",
                "content": "The average American spends $219/month on subscriptions — often $100+ more than they estimate. Small recurring charges are easy to forget but add up to thousands per year.",
                "key_takeaway": "Most people underestimate subscription spending by 2x.",
            },
            {
                "section_number": 2,
                "title": "The Audit Process",
                "content": "Review your last 3 months of bank statements. List every recurring charge. For each one, ask: Did I use this in the last 30 days? Would I sign up again today? If no to either, cancel it.",
                "key_takeaway": "If you haven't used it in 30 days, cancel it.",
            },
            {
                "section_number": 3,
                "title": "Preventing Resubscription",
                "content": "Unsubscribe from marketing emails after cancelling. Set a calendar reminder for free trial end dates. Use a dedicated email for subscriptions to track them easily.",
                "key_takeaway": "Unsubscribe from marketing to prevent resubscription.",
            },
        ],
    },
    {
        "code": "L-004",
        "title": "Mindful Spending",
        "description": "Learn the 24-hour rule and other techniques to reduce impulse purchases.",
        "category": LessonCategory.reduce_spending,
        "estimated_minutes": 6,
        "display_order": 4,
        "sections": [
            {
                "section_number": 1,
                "title": "The 24-Hour Rule",
                "content": "For any non-essential purchase over $50, wait 24 hours before buying. This simple pause eliminates up to 70% of impulse purchases. If you still want it after 24 hours, it's likely a considered decision.",
                "key_takeaway": "Wait 24 hours before non-essential purchases over $50.",
            },
            {
                "section_number": 2,
                "title": "Cost Per Use",
                "content": "Evaluate purchases by cost per use: divide the price by how many times you'll use it. A $100 item used 100 times costs $1/use. A $20 item used once costs $20/use. The cheaper item isn't always the better deal.",
                "key_takeaway": "Think in cost-per-use, not sticker price.",
            },
        ],
    },
    # --- pay_off_debt (2) ---
    {
        "code": "L-005",
        "title": "Debt Snowball vs. Avalanche",
        "description": "Compare the two most popular debt payoff strategies and choose the right one for you.",
        "category": LessonCategory.pay_off_debt,
        "estimated_minutes": 8,
        "display_order": 5,
        "sections": [
            {
                "section_number": 1,
                "title": "The Snowball Method",
                "content": "Pay minimum on all debts, then put extra money toward the smallest balance first. When it's paid off, roll that payment to the next smallest. This builds momentum through quick wins.",
                "key_takeaway": "Snowball: pay smallest balance first for psychological wins.",
            },
            {
                "section_number": 2,
                "title": "The Avalanche Method",
                "content": "Pay minimum on all debts, then put extra money toward the highest interest rate first. This saves the most money in interest over time but requires more patience for the first payoff.",
                "key_takeaway": "Avalanche: pay highest interest first to minimize total cost.",
            },
            {
                "section_number": 3,
                "title": "Which to Choose",
                "content": "If you need motivation and quick wins, choose snowball. If you're disciplined and want to minimize interest paid, choose avalanche. Both are vastly better than paying only minimums.",
                "key_takeaway": "Either strategy is far better than minimum payments only.",
            },
        ],
    },
    {
        "code": "L-006",
        "title": "Understanding Interest Rates",
        "description": "Learn how interest compounds and why high-rate debt should be prioritized.",
        "category": LessonCategory.pay_off_debt,
        "estimated_minutes": 7,
        "display_order": 6,
        "sections": [
            {
                "section_number": 1,
                "title": "Simple vs. Compound Interest",
                "content": "Simple interest charges on the original principal only. Compound interest charges on principal plus accumulated interest. Credit cards use compound interest — meaning you pay interest on interest. A $5,000 balance at 20% APR minimum payments only takes 25+ years to pay off.",
                "key_takeaway": "Compound interest on debt means you pay interest on interest.",
            },
            {
                "section_number": 2,
                "title": "The True Cost of Minimum Payments",
                "content": "Minimum payments are designed to maximize the interest you pay. On a $5,000 credit card at 20% APR, minimum payments cost $7,000+ in interest. Paying even $50 extra/month cuts payoff time in half.",
                "key_takeaway": "Small extra payments dramatically reduce total interest paid.",
            },
        ],
    },
    # --- build_emergency_fund (2) ---
    {
        "code": "L-007",
        "title": "Emergency Fund Basics",
        "description": "Why you need an emergency fund and how much to save.",
        "category": LessonCategory.build_emergency_fund,
        "estimated_minutes": 6,
        "display_order": 7,
        "sections": [
            {
                "section_number": 1,
                "title": "Why You Need One",
                "content": "An emergency fund prevents you from going into debt when unexpected expenses hit — car repairs, medical bills, job loss. Without one, a $400 emergency can start a debt spiral. With one, it's an inconvenience, not a crisis.",
                "key_takeaway": "Emergency funds prevent unexpected costs from becoming debt.",
            },
            {
                "section_number": 2,
                "title": "How Much to Save",
                "content": "Start with $1,000 as a starter fund. Then build to 3-6 months of essential expenses. If your income is variable or you're single-income, aim for 6 months. Two-income households may be comfortable with 3 months.",
                "key_takeaway": "Start with $1,000, then build to 3-6 months of expenses.",
            },
        ],
    },
    {
        "code": "L-008",
        "title": "Where to Keep Your Emergency Fund",
        "description": "Choose the right account type to keep your emergency fund accessible but growing.",
        "category": LessonCategory.build_emergency_fund,
        "estimated_minutes": 5,
        "display_order": 8,
        "sections": [
            {
                "section_number": 1,
                "title": "High-Yield Savings Accounts",
                "content": "Keep your emergency fund in a high-yield savings account (HYSA). These offer 4-5% APY vs. 0.01% at traditional banks. Your money stays FDIC-insured and accessible within 1-2 business days.",
                "key_takeaway": "Use a high-yield savings account for 100x+ better returns.",
            },
            {
                "section_number": 2,
                "title": "Keep It Separate",
                "content": "Don't keep emergency funds in your checking account — you'll spend it. Use a separate bank for your emergency fund to add a friction barrier. The 1-2 day transfer time helps prevent impulse withdrawals.",
                "key_takeaway": "Separate accounts create healthy friction against spending.",
            },
        ],
    },
    # --- budget_better (2) ---
    {
        "code": "L-009",
        "title": "Zero-Based Budgeting",
        "description": "Give every dollar a job — the most effective budgeting method for beginners.",
        "category": LessonCategory.budget_better,
        "estimated_minutes": 8,
        "display_order": 9,
        "sections": [
            {
                "section_number": 1,
                "title": "Every Dollar Gets a Job",
                "content": "In zero-based budgeting, income minus expenses equals zero. Every dollar is assigned to a category: rent, groceries, savings, entertainment, etc. This doesn't mean you spend everything — savings is a category too.",
                "key_takeaway": "Assign every dollar to a purpose — savings is a category.",
            },
            {
                "section_number": 2,
                "title": "Setting Up Your Budget",
                "content": "List your income sources. List all expenses by category. Assign amounts until your budget balances to zero. Track spending against your budget weekly. Adjust categories as needed — the first month is always rough.",
                "key_takeaway": "Track weekly and adjust — the first month is a learning month.",
            },
            {
                "section_number": 3,
                "title": "Common Mistakes",
                "content": "Don't forget irregular expenses (car insurance, annual subscriptions). Don't budget too tight on food or fun — you'll abandon it. Do include a 'buffer' category of 5-10% for surprises.",
                "key_takeaway": "Include irregular expenses and a buffer for surprises.",
            },
        ],
    },
    {
        "code": "L-010",
        "title": "Tracking Your Spending",
        "description": "Build awareness of where your money goes with simple tracking habits.",
        "category": LessonCategory.budget_better,
        "estimated_minutes": 5,
        "display_order": 10,
        "sections": [
            {
                "section_number": 1,
                "title": "Why Track?",
                "content": "Studies show that simply tracking spending reduces it by 10-15% — even without a budget. Awareness creates natural self-regulation. You can't improve what you don't measure.",
                "key_takeaway": "Tracking alone reduces spending 10-15%.",
            },
            {
                "section_number": 2,
                "title": "How to Track",
                "content": "Use your bank's transaction history or a finance app. Review once a week for 10 minutes. Categorize each purchase and note any surprises. The goal is awareness, not judgment.",
                "key_takeaway": "Review spending weekly — 10 minutes builds lasting awareness.",
            },
        ],
    },
]


async def seed_lessons(db: AsyncSession) -> int:
    """Seed lesson definitions. Idempotent — skips existing codes.

    Returns count of newly created lessons.
    """
    created = 0
    for lesson_data in LESSONS:
        result = await db.execute(
            select(LessonDefinition).where(LessonDefinition.code == lesson_data["code"])
        )
        if result.scalar_one_or_none() is not None:
            continue

        sections = lesson_data["sections"]
        lesson = LessonDefinition(
            code=lesson_data["code"],
            title=lesson_data["title"],
            description=lesson_data["description"],
            category=lesson_data["category"],
            sections=sections,
            total_sections=len(sections),
            estimated_minutes=lesson_data["estimated_minutes"],
            display_order=lesson_data["display_order"],
        )
        db.add(lesson)
        created += 1

    await db.flush()
    return created
