"""Derived view builders for the Money Graph.

All views:
- Resolve FKs to human-readable names (merchant, category)
- Strip raw provider IDs
- Include confidence and assumptions where applicable
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.merchant import Merchant
from app.models.recurring import RecurringPattern
from app.models.transaction import Transaction, TransactionType
from app.services.recurring_service import (
    INTERVAL_TOLERANCE_DAYS,
    AMOUNT_TOLERANCE_FRACTION,
)


async def account_summary_view(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict]:
    """Accounts with balances, types, last synced. No raw provider IDs."""
    result = await db.execute(
        select(Account)
        .where(Account.user_id == user_id)
        .order_by(Account.created_at.asc())
    )
    accounts = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "account_type": a.account_type.value,
            "institution_name": a.institution_name,
            "account_name": a.account_name,
            "current_balance": str(a.current_balance),
            "available_balance": str(a.available_balance) if a.available_balance else None,
            "currency": a.currency,
            "is_manual": a.is_manual,
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        }
        for a in accounts
    ]


async def transaction_list_view(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Transactions with resolved merchant name, category name, formatted amounts.

    No raw provider transaction IDs exposed.
    """
    stmt = (
        select(Transaction, Merchant, Category)
        .outerjoin(Merchant, Transaction.merchant_id == Merchant.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc())
    )
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": str(txn.id),
            "account_id": str(txn.account_id),
            "merchant_name": merchant.display_name if merchant else None,
            "category_name": category.name if category else None,
            "raw_description": txn.raw_description,
            "normalized_description": txn.normalized_description,
            "amount": str(txn.amount),
            "currency": txn.currency,
            "transaction_date": txn.transaction_date.isoformat()
            if txn.transaction_date else None,
            "posted_date": txn.posted_date.isoformat() if txn.posted_date else None,
            "is_pending": txn.is_pending,
            "transaction_type": txn.transaction_type.value,
        }
        for txn, merchant, category in rows
    ]


async def recurring_patterns_view(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[dict]:
    """Patterns with merchant name, confidence, next expected date.

    Confidence and assumptions always exposed.
    """
    result = await db.execute(
        select(RecurringPattern, Merchant, Category)
        .outerjoin(Merchant, RecurringPattern.merchant_id == Merchant.id)
        .outerjoin(Category, RecurringPattern.category_id == Category.id)
        .where(
            RecurringPattern.user_id == user_id,
            RecurringPattern.is_active == True,  # noqa: E712
        )
        .order_by(RecurringPattern.estimated_amount.desc())
    )
    rows = result.all()

    return [
        {
            "id": str(pattern.id),
            "merchant_name": merchant.display_name if merchant else None,
            "category_name": category.name if category else None,
            "estimated_amount": str(pattern.estimated_amount),
            "amount_variance": str(pattern.amount_variance),
            "frequency": pattern.frequency.value,
            "confidence": pattern.confidence.value,
            "assumptions": {
                "interval_tolerance_days": INTERVAL_TOLERANCE_DAYS,
                "amount_tolerance_pct": float(AMOUNT_TOLERANCE_FRACTION) * 100,
                "detection_method": "interval_analysis",
            },
            "next_expected_date": pattern.next_expected_date.isoformat()
            if pattern.next_expected_date else None,
            "last_observed_date": pattern.last_observed_date.isoformat()
            if pattern.last_observed_date else None,
            "is_active": pattern.is_active,
        }
        for pattern, merchant, category in rows
    ]


async def money_graph_summary_view(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Aggregate summary: total balance, monthly income/spending, top categories, top merchants.

    Includes assumptions and confidence where applicable.
    """
    # Total balance across all accounts
    result = await db.execute(
        select(func.sum(Account.current_balance))
        .where(Account.user_id == user_id)
    )
    total_balance = result.scalar() or Decimal("0.00")

    # Monthly income and spending (last 30 days)
    now = datetime.now(timezone.utc)
    thirty_days_ago = now.replace(day=1) if now.day > 1 else now

    # Get all transactions for this period
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= thirty_days_ago,
        )
    )
    recent_txns = result.scalars().all()

    monthly_income = sum(
        t.amount for t in recent_txns if t.transaction_type == TransactionType.credit
    )
    monthly_spending = sum(
        t.amount for t in recent_txns if t.transaction_type == TransactionType.debit
    )

    # Top categories by spend
    category_spend: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for t in recent_txns:
        if t.transaction_type == TransactionType.debit and t.category_id:
            category_spend[t.category_id] += t.amount

    top_category_ids = sorted(category_spend, key=lambda k: category_spend[k], reverse=True)[:5]
    top_categories = []
    for cid in top_category_ids:
        result = await db.execute(select(Category).where(Category.id == cid))
        cat = result.scalar_one_or_none()
        if cat:
            top_categories.append({
                "name": cat.name,
                "total_spent": str(category_spend[cid]),
            })

    # Top merchants by spend
    merchant_spend: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for t in recent_txns:
        if t.transaction_type == TransactionType.debit and t.merchant_id:
            merchant_spend[t.merchant_id] += t.amount

    top_merchant_ids = sorted(merchant_spend, key=lambda k: merchant_spend[k], reverse=True)[:5]
    top_merchants = []
    for mid in top_merchant_ids:
        result = await db.execute(select(Merchant).where(Merchant.id == mid))
        m = result.scalar_one_or_none()
        if m:
            top_merchants.append({
                "name": m.display_name,
                "total_spent": str(merchant_spend[mid]),
            })

    return {
        "total_balance": str(total_balance),
        "monthly_income": str(monthly_income),
        "monthly_spending": str(monthly_spending),
        "top_categories": top_categories,
        "top_merchants": top_merchants,
        "assumptions": {
            "period": "current_calendar_month",
            "balance_includes": "all_accounts",
        },
    }
