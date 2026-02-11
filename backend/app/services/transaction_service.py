"""Transaction normalization and categorization service.

- Ingests raw transactions, normalizes descriptions, resolves merchants, auto-categorizes
- Auto-categorization: merchant -> category mapping (configurable). Falls back to "Other".
- User recategorization logged to audit
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.merchant import Merchant
from app.models.transaction import Transaction, TransactionType
from app.services import audit_service, merchant_service

# Default merchant-to-category mapping (normalized merchant name -> category name)
MERCHANT_CATEGORY_MAP: dict[str, str] = {
    "starbucks": "Dining",
    "mcdonalds": "Dining",
    "uber eats": "Dining",
    "doordash": "Dining",
    "grubhub": "Dining",
    "walmart": "Groceries",
    "kroger": "Groceries",
    "whole foods": "Groceries",
    "trader joe's": "Groceries",
    "amazon": "Shopping",
    "target": "Shopping",
    "uber": "Transport",
    "lyft": "Transport",
    "shell": "Transport",
    "chevron": "Transport",
    "netflix": "Entertainment",
    "spotify": "Entertainment",
    "hulu": "Entertainment",
    "comcast": "Utilities",
    "at&t": "Utilities",
    "verizon": "Utilities",
    "cvs": "Healthcare",
    "walgreens": "Healthcare",
}


async def _resolve_category(
    db: AsyncSession,
    merchant_normalized: str | None,
) -> Category | None:
    """Auto-assign category based on merchant. Falls back to 'Other'."""
    category_name = "Other"
    if merchant_normalized and merchant_normalized in MERCHANT_CATEGORY_MAP:
        category_name = MERCHANT_CATEGORY_MAP[merchant_normalized]

    result = await db.execute(
        select(Category).where(
            Category.name == category_name,
            Category.is_system == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def ingest_transaction(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    raw_description: str,
    amount: Decimal,
    transaction_type: TransactionType,
    transaction_date: datetime,
    posted_date: datetime | None = None,
    is_pending: bool = False,
    currency: str = "USD",
    provider_transaction_id: str | None = None,
    category_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> Transaction:
    """Ingest a transaction: normalize description, resolve merchant, auto-categorize, store."""
    # Resolve merchant
    merchant = await merchant_service.get_or_create_merchant(
        db, raw_description, user_id=user_id
    )

    # Normalize description = merchant display name
    normalized_description = merchant.display_name

    # Auto-categorize (if no explicit category provided)
    if category_id is None:
        category = await _resolve_category(db, merchant.normalized_name)
        category_id = category.id if category else None

    txn = Transaction(
        account_id=account_id,
        user_id=user_id,
        merchant_id=merchant.id,
        category_id=category_id,
        raw_description=raw_description,
        normalized_description=normalized_description,
        amount=amount,
        currency=currency,
        transaction_date=transaction_date,
        posted_date=posted_date,
        is_pending=is_pending,
        transaction_type=transaction_type,
        provider_transaction_id=provider_transaction_id,
    )
    db.add(txn)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="transaction.created",
        entity_type="Transaction",
        entity_id=txn.id,
        action="create",
        detail={
            "raw_description": raw_description,
            "merchant": merchant.normalized_name,
            "amount": str(amount),
            "type": transaction_type.value,
        },
        ip_address=ip_address,
    )

    return txn


async def recategorize(
    db: AsyncSession,
    *,
    transaction_id: uuid.UUID,
    category_id: uuid.UUID,
    user_id: uuid.UUID,
    ip_address: str | None = None,
) -> Transaction:
    """User override: recategorize a transaction. Logged to audit."""
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
    )
    txn = result.scalar_one()

    old_category_id = txn.category_id
    txn.category_id = category_id
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="transaction.recategorized",
        entity_type="Transaction",
        entity_id=txn.id,
        action="recategorize",
        detail={
            "old_category_id": str(old_category_id) if old_category_id else None,
            "new_category_id": str(category_id),
        },
        ip_address=ip_address,
    )

    return txn


async def get_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Transaction]:
    """Get transactions for a user with optional filters."""
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc())
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())
