from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import AccountType
from app.models.connection import Connection, ConnectionStatus
from app.models.user import User
from app.services import account_service, audit_service


async def _create_user(db: AsyncSession) -> User:
    user = User(email="acct-svc@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_manual_account(db_session: AsyncSession):
    user = await _create_user(db_session)
    acct = await account_service.create_manual_account(
        db_session,
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main Checking",
        current_balance=Decimal("1500.00"),
    )
    await db_session.commit()

    assert acct.is_manual is True
    assert acct.institution_name == "Chase"
    assert acct.current_balance == Decimal("1500.00")
    assert acct.connection_id is None


@pytest.mark.asyncio
async def test_update_manual_balance(db_session: AsyncSession):
    user = await _create_user(db_session)
    acct = await account_service.create_manual_account(
        db_session,
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main",
        current_balance=Decimal("1000.00"),
    )
    await db_session.commit()

    updated = await account_service.update_manual_balance(
        db_session,
        account_id=acct.id,
        new_balance=Decimal("1200.00"),
        user_id=user.id,
    )
    await db_session.commit()

    assert updated.current_balance == Decimal("1200.00")

    # Verify audit trail
    events = await audit_service.get_events_for_user(db_session, user.id)
    balance_events = [e for e in events if e.event_type == "account.balance_updated"]
    assert len(balance_events) == 1
    assert balance_events[0].detail["old_balance"] == "1000.00"
    assert balance_events[0].detail["new_balance"] == "1200.00"


@pytest.mark.asyncio
async def test_create_linked_account(db_session: AsyncSession):
    user = await _create_user(db_session)
    conn = Connection(
        user_id=user.id,
        provider="plaid",
        provider_connection_id="conn_123",
        status=ConnectionStatus.active,
    )
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)

    acct = await account_service.create_linked_account(
        db_session,
        user_id=user.id,
        connection_id=conn.id,
        account_type=AccountType.savings,
        institution_name="BoA",
        account_name="Savings",
        current_balance=Decimal("5000.00"),
    )
    await db_session.commit()

    assert acct.is_manual is False
    assert acct.connection_id == conn.id
    assert acct.last_synced_at is not None


@pytest.mark.asyncio
async def test_get_accounts(db_session: AsyncSession):
    user = await _create_user(db_session)

    await account_service.create_manual_account(
        db_session,
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Checking",
        current_balance=Decimal("1000.00"),
    )
    await account_service.create_manual_account(
        db_session,
        user_id=user.id,
        account_type=AccountType.credit_card,
        institution_name="Amex",
        account_name="Platinum",
        current_balance=Decimal("500.00"),
    )
    await db_session.commit()

    accounts = await account_service.get_accounts(db_session, user.id)
    assert len(accounts) == 2
