import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import merchant_service
from app.services.merchant_service import normalize_name


async def _create_user(db: AsyncSession) -> User:
    user = User(email="merch@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_normalize_strips_store_numbers():
    assert normalize_name("STARBUCKS #1234 NYC") == "starbucks"
    assert normalize_name("STARBUCKS #5678 LA") == "starbucks"


@pytest.mark.asyncio
async def test_normalize_strips_reference_codes():
    assert normalize_name("AMAZON.COM*AB1CD") == "amazon"
    assert normalize_name("AMZN MKTP US*XY9Z") == "amazon"


@pytest.mark.asyncio
async def test_normalize_alias_matching():
    assert normalize_name("AMAZON.COM*stuff") == "amazon"
    assert normalize_name("AMZN MKTP US*XY9Z") == "amazon"
    assert normalize_name("WAL-MART") == "walmart"
    assert normalize_name("WM SUPERCENTER") == "walmart"


@pytest.mark.asyncio
async def test_normalize_unknown_merchant():
    result = normalize_name("SOME LOCAL SHOP")
    assert result == "some local shop"


@pytest.mark.asyncio
async def test_get_or_create_same_merchant(db_session: AsyncSession):
    """Two raw names for same merchant -> same Merchant record."""
    user = await _create_user(db_session)

    m1 = await merchant_service.get_or_create_merchant(
        db_session, "STARBUCKS #1234 NYC", user_id=user.id
    )
    await db_session.commit()

    m2 = await merchant_service.get_or_create_merchant(
        db_session, "STARBUCKS #5678 LA", user_id=user.id
    )
    await db_session.commit()

    assert m1.id == m2.id
    assert m1.normalized_name == "starbucks"


@pytest.mark.asyncio
async def test_get_or_create_amazon_aliases(db_session: AsyncSession):
    """Amazon aliases all resolve to same merchant."""
    user = await _create_user(db_session)

    m1 = await merchant_service.get_or_create_merchant(
        db_session, "AMAZON.COM*AB1CD", user_id=user.id
    )
    await db_session.commit()

    m2 = await merchant_service.get_or_create_merchant(
        db_session, "AMZN MKTP US*XY9Z", user_id=user.id
    )
    await db_session.commit()

    assert m1.id == m2.id
    assert m1.normalized_name == "amazon"


@pytest.mark.asyncio
async def test_get_or_create_new_unknown(db_session: AsyncSession):
    """Unknown merchant creates a new record."""
    user = await _create_user(db_session)

    m = await merchant_service.get_or_create_merchant(
        db_session, "UNIQUE COFFEE PLACE", user_id=user.id
    )
    await db_session.commit()

    assert m.normalized_name == "unique coffee place"
    assert m.display_name == "Unique Coffee Place"
