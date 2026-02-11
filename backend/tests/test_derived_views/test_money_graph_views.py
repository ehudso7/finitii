"""Tests for derived views: UI reads only these, never raw provider data."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.derived_views.money_graph import (
    account_summary_view,
    money_graph_summary_view,
    recurring_patterns_view,
    transaction_list_view,
)
from app.models.account import Account, AccountType
from app.models.transaction import TransactionType
from app.models.user import User
from app.services import category_service, recurring_service, transaction_service


async def _setup(db: AsyncSession):
    user = User(email="views@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    acct = Account(
        user_id=user.id,
        account_type=AccountType.checking,
        institution_name="Chase",
        account_name="Main Checking",
        current_balance=Decimal("3000.00"),
        is_manual=True,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)

    await category_service.seed_system_categories(db)
    await db.commit()

    return user, acct


@pytest.mark.asyncio
async def test_account_summary_no_provider_ids(db_session: AsyncSession):
    """Account summary view does not expose raw provider IDs."""
    user, acct = await _setup(db_session)

    views = await account_summary_view(db_session, user.id)
    assert len(views) == 1
    v = views[0]

    assert "id" in v
    assert "account_type" in v
    assert "institution_name" in v
    assert v["current_balance"] == "3000.00"
    # No connection_id or provider-specific fields
    assert "connection_id" not in v
    assert "provider_connection_id" not in v


@pytest.mark.asyncio
async def test_transaction_list_resolves_names(db_session: AsyncSession):
    """Transaction view resolves merchant + category names, no provider txn IDs."""
    user, acct = await _setup(db_session)

    await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="STARBUCKS #1234 NYC",
        amount=Decimal("5.75"),
        transaction_type=TransactionType.debit,
        transaction_date=datetime.now(timezone.utc),
        provider_transaction_id="prov_txn_secret_123",
    )
    await db_session.commit()

    views = await transaction_list_view(db_session, user.id)
    assert len(views) == 1
    v = views[0]

    assert v["merchant_name"] == "Starbucks"
    assert v["category_name"] == "Dining"
    assert v["amount"] == "5.75"
    # No provider_transaction_id exposed
    assert "provider_transaction_id" not in v


@pytest.mark.asyncio
async def test_recurring_patterns_expose_confidence(db_session: AsyncSession):
    """Recurring view exposes confidence + assumptions."""
    user, acct = await _setup(db_session)

    base_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
    for i in range(4):
        await transaction_service.ingest_transaction(
            db_session,
            account_id=acct.id,
            user_id=user.id,
            raw_description=f"NETFLIX #{i}",
            amount=Decimal("15.99"),
            transaction_type=TransactionType.debit,
            transaction_date=base_date + timedelta(days=30 * i),
        )
    await db_session.commit()

    await recurring_service.detect_patterns(db_session, user.id)
    await db_session.commit()

    views = await recurring_patterns_view(db_session, user.id)
    assert len(views) >= 1
    v = views[0]

    assert "confidence" in v
    assert v["confidence"] in ("low", "medium", "high")
    assert "assumptions" in v
    assert "interval_tolerance_days" in v["assumptions"]
    assert "amount_tolerance_pct" in v["assumptions"]
    assert v["merchant_name"] is not None
    # No raw merchant_id or provider IDs
    assert "merchant_id" not in v
    assert "provider_transaction_id" not in v


@pytest.mark.asyncio
async def test_money_graph_summary(db_session: AsyncSession):
    """Summary view computes totals and includes assumptions."""
    user, acct = await _setup(db_session)

    # Add some recent transactions
    now = datetime.now(timezone.utc)
    await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="STARBUCKS #1",
        amount=Decimal("5.00"),
        transaction_type=TransactionType.debit,
        transaction_date=now,
    )
    await transaction_service.ingest_transaction(
        db_session,
        account_id=acct.id,
        user_id=user.id,
        raw_description="PAYROLL DEPOSIT",
        amount=Decimal("2000.00"),
        transaction_type=TransactionType.credit,
        transaction_date=now,
    )
    await db_session.commit()

    summary = await money_graph_summary_view(db_session, user.id)

    assert summary["total_balance"] == "3000.00"
    assert "assumptions" in summary
    assert summary["assumptions"]["balance_includes"] == "all_accounts"
    assert "monthly_income" in summary
    assert "monthly_spending" in summary
    assert "top_categories" in summary
    assert "top_merchants" in summary
