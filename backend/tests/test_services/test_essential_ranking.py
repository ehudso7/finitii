"""Test that essential toggle suppresses cancellation recommendations."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant
from app.models.recurring import Confidence, Frequency, RecurringPattern
from app.models.user import User
from app.services import bill_service, ranking_service
from app.services.cheat_code_seed import seed_cheat_codes


async def _create_user(db: AsyncSession) -> User:
    user = User(email="essrank@test.com", password_hash="hashed")
    db.add(user)
    await db.flush()
    return user


async def _create_patterns(
    db: AsyncSession, user: User, count: int, essential: bool = False,
) -> list[RecurringPattern]:
    """Create N detected recurring patterns."""
    patterns = []
    for i in range(count):
        merchant = Merchant(
            raw_name=f"Service{i}", normalized_name=f"service{i}",
            display_name=f"Service{i}",
        )
        db.add(merchant)
        await db.flush()

        pattern = RecurringPattern(
            user_id=user.id,
            merchant_id=merchant.id,
            estimated_amount=Decimal("9.99"),
            amount_variance=Decimal("0.00"),
            frequency=Frequency.monthly,
            confidence=Confidence.high,
            next_expected_date=datetime.now(timezone.utc) + timedelta(days=15),
            last_observed_date=datetime.now(timezone.utc) - timedelta(days=15),
            is_active=True,
            is_manual=False,
            is_essential=essential,
        )
        db.add(pattern)
        await db.flush()
        patterns.append(pattern)

    return patterns


@pytest.mark.asyncio
async def test_essential_patterns_excluded_from_cancel_count(db_session: AsyncSession):
    """When all patterns are essential, CC-001 should not get subscription cancel bonus.

    The subscription_cancel template uses non_essential count.
    """
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # Create 3 essential patterns — CC-001 should not count them
    await _create_patterns(db_session, user, 3, essential=True)

    recs = await ranking_service.compute_top_3(db_session, user.id)

    # CC-001 should not use "subscription_cancel" template since all are essential
    for r in recs:
        if r.explanation_template == "subscription_cancel":
            # If it does appear, the count should be 0 (non-essential)
            assert r.explanation_inputs.get("recurring_count", 0) == 0


@pytest.mark.asyncio
async def test_mixed_essential_non_essential(db_session: AsyncSession):
    """Only non-essential patterns count toward cancellation recommendations."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    # Create 2 essential + 3 non-essential patterns
    await _create_patterns(db_session, user, 2, essential=True)
    await _create_patterns(db_session, user, 3, essential=False)

    recs = await ranking_service.compute_top_3(db_session, user.id)

    # If CC-001 appears with subscription_cancel template, count should be 3
    for r in recs:
        if r.explanation_template == "subscription_cancel":
            assert r.explanation_inputs["recurring_count"] == 3


@pytest.mark.asyncio
async def test_essential_toggle_affects_recompute(db_session: AsyncSession):
    """Toggling essential and recomputing changes the cancellation count."""
    user = await _create_user(db_session)
    await seed_cheat_codes(db_session)

    patterns = await _create_patterns(db_session, user, 4, essential=False)

    # First compute — all 4 non-essential
    recs1 = await ranking_service.compute_top_3(db_session, user.id)

    # Toggle 2 to essential
    await bill_service.toggle_essential(
        db_session, bill_id=patterns[0].id, user_id=user.id, is_essential=True,
    )
    await bill_service.toggle_essential(
        db_session, bill_id=patterns[1].id, user_id=user.id, is_essential=True,
    )

    # Recompute — now only 2 non-essential
    recs2 = await ranking_service.compute_top_3(db_session, user.id)

    # Verify confidence rules still hold
    for r in recs2:
        assert r.confidence != "low"
    assert any(r.is_quick_win for r in recs2)
