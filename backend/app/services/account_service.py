"""Account service: create manual/linked accounts, update balance, list.

All operations audit-logged.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.connection import Connection
from app.services import audit_service


async def create_manual_account(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    account_type: AccountType,
    institution_name: str,
    account_name: str,
    current_balance: Decimal = Decimal("0.00"),
    available_balance: Decimal | None = None,
    currency: str = "USD",
    ip_address: str | None = None,
) -> Account:
    """Create a manual account (is_manual=True, no connection)."""
    acct = Account(
        user_id=user_id,
        account_type=account_type,
        institution_name=institution_name,
        account_name=account_name,
        current_balance=current_balance,
        available_balance=available_balance,
        currency=currency,
        is_manual=True,
        connection_id=None,
    )
    db.add(acct)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="account.created",
        entity_type="Account",
        entity_id=acct.id,
        action="create",
        detail={
            "account_type": account_type.value,
            "institution": institution_name,
            "is_manual": True,
        },
        ip_address=ip_address,
    )

    return acct


async def update_manual_balance(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    new_balance: Decimal,
    user_id: uuid.UUID,
    available_balance: Decimal | None = None,
    ip_address: str | None = None,
) -> Account:
    """Update the balance on a manual account. Logged to audit."""
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    acct = result.scalar_one()

    old_balance = acct.current_balance
    acct.current_balance = new_balance
    if available_balance is not None:
        acct.available_balance = available_balance
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="account.balance_updated",
        entity_type="Account",
        entity_id=acct.id,
        action="update_balance",
        detail={
            "old_balance": str(old_balance),
            "new_balance": str(new_balance),
        },
        ip_address=ip_address,
    )

    return acct


async def create_linked_account(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    connection_id: uuid.UUID,
    account_type: AccountType,
    institution_name: str,
    account_name: str,
    current_balance: Decimal = Decimal("0.00"),
    available_balance: Decimal | None = None,
    currency: str = "USD",
    ip_address: str | None = None,
) -> Account:
    """Create a linked account from a provider connection."""
    acct = Account(
        user_id=user_id,
        connection_id=connection_id,
        account_type=account_type,
        institution_name=institution_name,
        account_name=account_name,
        current_balance=current_balance,
        available_balance=available_balance,
        currency=currency,
        is_manual=False,
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(acct)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="account.created",
        entity_type="Account",
        entity_id=acct.id,
        action="create",
        detail={
            "account_type": account_type.value,
            "institution": institution_name,
            "is_manual": False,
            "connection_id": str(connection_id),
        },
        ip_address=ip_address,
    )

    return acct


async def get_accounts(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Account]:
    """Get all accounts for a user."""
    result = await db.execute(
        select(Account)
        .where(Account.user_id == user_id)
        .order_by(Account.created_at.asc())
    )
    return list(result.scalars().all())
