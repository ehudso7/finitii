import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant


@pytest.mark.asyncio
async def test_create_merchant(db_session: AsyncSession):
    merchant = Merchant(
        raw_name="STARBUCKS #1234 NYC",
        normalized_name="starbucks",
        display_name="Starbucks",
    )
    db_session.add(merchant)
    await db_session.commit()

    result = await db_session.execute(
        select(Merchant).where(Merchant.normalized_name == "starbucks")
    )
    fetched = result.scalar_one()
    assert fetched.raw_name == "STARBUCKS #1234 NYC"
    assert fetched.display_name == "Starbucks"
    assert fetched.created_at is not None
