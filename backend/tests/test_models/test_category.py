import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.user import User


async def _create_user(db: AsyncSession) -> User:
    user = User(email="cat@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_system_category(db_session: AsyncSession):
    cat = Category(name="Groceries", is_system=True, icon="cart")
    db_session.add(cat)
    await db_session.commit()

    result = await db_session.execute(select(Category).where(Category.name == "Groceries"))
    fetched = result.scalar_one()
    assert fetched.is_system is True
    assert fetched.user_id is None  # system category


@pytest.mark.asyncio
async def test_create_user_category(db_session: AsyncSession):
    user = await _create_user(db_session)
    cat = Category(name="Coffee", user_id=user.id, is_system=False)
    db_session.add(cat)
    await db_session.commit()

    result = await db_session.execute(select(Category).where(Category.name == "Coffee"))
    fetched = result.scalar_one()
    assert fetched.is_system is False
    assert fetched.user_id == user.id


@pytest.mark.asyncio
async def test_category_self_ref_parent(db_session: AsyncSession):
    parent = Category(name="Food", is_system=True)
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    child = Category(name="Fast Food", is_system=True, parent_id=parent.id)
    db_session.add(child)
    await db_session.commit()

    result = await db_session.execute(select(Category).where(Category.name == "Fast Food"))
    fetched = result.scalar_one()
    assert fetched.parent_id == parent.id
