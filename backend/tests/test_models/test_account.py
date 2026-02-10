import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.connection import Connection, ConnectionStatus
from app.models.user import User


async def _create_user(db: AsyncSession, email: str = "acct@example.com") -> User:
    user = User(email=email, password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_manual_account(db_session: AsyncSession):
    user = await _create_user(db_session)
    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main Checking",
        current_balance=Decimal("1500.50"),
        currency="USD",
        is_manual=True,
    )
    db_session.add(acct)
    await db_session.commit()

    result = await db_session.execute(select(Account).where(Account.user_id == user.id))
    fetched = result.scalar_one()
    assert fetched.account_type == AccountType.checking
    assert fetched.institution_name == "Chase"
    assert fetched.current_balance == Decimal("1500.50")
    assert fetched.is_manual is True
    assert fetched.connection_id is None


@pytest.mark.asyncio
async def test_account_with_connection(db_session: AsyncSession):
    user = await _create_user(db_session, "linked@example.com")
    conn = Connection(
        user_id=user.id,
        provider="plaid",
        provider_connection_id="conn_x",
        status=ConnectionStatus.active,
    )
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)

    acct = Account(
        user_id=user.id,
        connection_id=conn.id,
        account_type=AccountType.savings,
        institution_name="BoA",
        account_name="Savings",
        current_balance=Decimal("5000.00"),
        is_manual=False,
    )
    db_session.add(acct)
    await db_session.commit()

    result = await db_session.execute(select(Account).where(Account.connection_id == conn.id))
    fetched = result.scalar_one()
    assert fetched.is_manual is False
    assert fetched.connection_id == conn.id


@pytest.mark.asyncio
async def test_account_fk_to_user(db_session: AsyncSession):
    acct = Account(
        user_id=uuid.uuid4(),
        account_type=AccountType.checking,
        institution_name="Fake",
        account_name="Bad",
        current_balance=Decimal("0"),
    )
    db_session.add(acct)
    with pytest.raises(IntegrityError):
        await db_session.commit()
