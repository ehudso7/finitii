import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category
from app.models.merchant import Merchant
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


async def _setup(db: AsyncSession):
    user = User(email="txn@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main",
        current_balance=Decimal("1000.00"),
        is_manual=True,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)

    merchant = Merchant(
        raw_name="STARBUCKS #1234",
        normalized_name="starbucks",
        display_name="Starbucks",
    )
    db.add(merchant)

    category = Category(name="Dining", is_system=True)
    db.add(category)
    await db.commit()
    await db.refresh(merchant)
    await db.refresh(category)

    return user, acct, merchant, category


@pytest.mark.asyncio
async def test_create_transaction(db_session: AsyncSession):
    user, acct, merchant, category = await _setup(db_session)

    txn = Transaction(
        account_id=acct.id,
        user_id=user.id,
        merchant_id=merchant.id,
        category_id=category.id,
        raw_description="STARBUCKS #1234 NYC",
        normalized_description="Starbucks",
        amount=Decimal("5.75"),
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.commit()

    result = await db_session.execute(select(Transaction).where(Transaction.user_id == user.id))
    fetched = result.scalar_one()
    assert fetched.amount == Decimal("5.75")
    assert fetched.transaction_type == TransactionType.debit
    assert fetched.merchant_id == merchant.id
    assert fetched.category_id == category.id


@pytest.mark.asyncio
async def test_transaction_decimal_precision(db_session: AsyncSession):
    user, acct, _, _ = await _setup(db_session)

    txn = Transaction(
        account_id=acct.id,
        user_id=user.id,
        raw_description="Precision test",
        normalized_description="Precision test",
        amount=Decimal("1234.56"),
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.credit,
    )
    db_session.add(txn)
    await db_session.commit()

    result = await db_session.execute(
        select(Transaction).where(Transaction.raw_description == "Precision test")
    )
    fetched = result.scalar_one()
    assert fetched.amount == Decimal("1234.56")


@pytest.mark.asyncio
async def test_transaction_fk_to_account(db_session: AsyncSession):
    user = User(email="txn-fk@example.com", password_hash="fakehash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    txn = Transaction(
        account_id=uuid.uuid4(),  # non-existent
        user_id=user.id,
        raw_description="Bad txn",
        normalized_description="Bad txn",
        amount=Decimal("10.00"),
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    with pytest.raises(IntegrityError):
        await db_session.commit()
