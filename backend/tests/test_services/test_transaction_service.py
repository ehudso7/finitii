from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.transaction import TransactionType
from app.models.user import User
from app.services import audit_service, category_service, transaction_service


async def _setup(db: AsyncSession):
    user = User(email="txn-svc@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main",
        current_balance=Decimal("2000.00"),
        is_manual=True,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)

    # Seed system categories
    await category_service.seed_system_categories(db)
    await db.commit()

    return user, acct


@pytest.mark.asyncio
async def test_ingest_resolves_merchant_and_categorizes(db_session: AsyncSession):
    """Ingest raw transaction -> merchant resolved -> category assigned."""
    user, acct = await _setup(db_session)

    txn = await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="STARBUCKS #1234 NYC",
        amount=Decimal("5.75"),
        transaction_type=TransactionType.debit,
        transaction_date=datetime.now(timezone.utc),
    )
    await db_session.commit()

    assert txn.merchant_id is not None
    assert txn.category_id is not None
    assert txn.normalized_description == "Starbucks"

    # Verify it was categorized as Dining
    cat = await category_service.get_category_by_id(db_session, txn.category_id)
    assert cat.name == "Dining"


@pytest.mark.asyncio
async def test_ingest_unknown_merchant_falls_back_to_other(db_session: AsyncSession):
    """Unknown merchant -> category falls back to 'Other'."""
    user, acct = await _setup(db_session)

    txn = await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="RANDOM LOCAL STORE",
        amount=Decimal("20.00"),
        transaction_type=TransactionType.debit,
        transaction_date=datetime.now(timezone.utc),
    )
    await db_session.commit()

    cat = await category_service.get_category_by_id(db_session, txn.category_id)
    assert cat.name == "Other"


@pytest.mark.asyncio
async def test_recategorize_updates_and_logs(db_session: AsyncSession):
    """User recategorizes -> new category sticks -> audit logged."""
    user, acct = await _setup(db_session)

    txn = await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="STARBUCKS #1234",
        amount=Decimal("6.00"),
        transaction_type=TransactionType.debit,
        transaction_date=datetime.now(timezone.utc),
    )
    await db_session.commit()

    # Get the Groceries category
    groceries = await category_service.get_category_by_name(db_session, "Groceries")
    assert groceries is not None

    # Recategorize
    updated = await transaction_service.recategorize(
        db_session,
        transaction_id=txn.id,
        category_id=groceries.id,
        user_id=user.id,
    )
    await db_session.commit()

    assert updated.category_id == groceries.id

    # Check audit
    events = await audit_service.get_events_for_user(db_session, user.id)
    recat_events = [e for e in events if e.event_type == "transaction.recategorized"]
    assert len(recat_events) == 1


@pytest.mark.asyncio
async def test_get_transactions_filtered(db_session: AsyncSession):
    """Get transactions with account filter."""
    user, acct = await _setup(db_session)

    for i in range(3):
        await transaction_service.ingest_transaction(
            db_session,
            account_id=acct.id,
            user_id=user.id,
            raw_description=f"TXN {i}",
            amount=Decimal(f"{(i + 1) * 10}.00"),
            transaction_type=TransactionType.debit,
            transaction_date=datetime.now(timezone.utc),
        )
    await db_session.commit()

    txns = await transaction_service.get_transactions(
        db_session, user.id, account_id=acct.id
    )
    assert len(txns) == 3
