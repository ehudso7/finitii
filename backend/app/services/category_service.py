"""Category service: seed system categories, create custom, lookup.

System categories are not deletable by users.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, SYSTEM_CATEGORIES
from app.services import audit_service


async def seed_system_categories(db: AsyncSession) -> list[Category]:
    """Seed all system categories if they don't already exist. Idempotent."""
    result = await db.execute(
        select(Category).where(Category.is_system == True)  # noqa: E712
    )
    existing = {c.name for c in result.scalars().all()}

    created = []
    for cat_def in SYSTEM_CATEGORIES:
        if cat_def["name"] not in existing:
            cat = Category(
                name=cat_def["name"],
                icon=cat_def.get("icon"),
                is_system=True,
                user_id=None,
            )
            db.add(cat)
            created.append(cat)

    if created:
        await db.flush()

    return created


async def get_system_categories(db: AsyncSession) -> list[Category]:
    """Return all system categories."""
    result = await db.execute(
        select(Category)
        .where(Category.is_system == True)  # noqa: E712
        .order_by(Category.name)
    )
    return list(result.scalars().all())


async def get_categories_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Category]:
    """Return system categories + user's custom categories."""
    result = await db.execute(
        select(Category)
        .where(
            (Category.is_system == True) | (Category.user_id == user_id)  # noqa: E712
        )
        .order_by(Category.name)
    )
    return list(result.scalars().all())


async def get_category_by_id(db: AsyncSession, category_id: uuid.UUID) -> Category | None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def get_category_by_name(
    db: AsyncSession, name: str, user_id: uuid.UUID | None = None
) -> Category | None:
    """Find a category by name. Checks system categories first, then user's."""
    # Try system category
    result = await db.execute(
        select(Category).where(
            Category.name == name,
            Category.is_system == True,  # noqa: E712
        )
    )
    cat = result.scalar_one_or_none()
    if cat is not None:
        return cat

    # Try user category
    if user_id is not None:
        result = await db.execute(
            select(Category).where(
                Category.name == name,
                Category.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    return None


async def create_user_category(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    parent_id: uuid.UUID | None = None,
    icon: str | None = None,
    ip_address: str | None = None,
) -> Category:
    """Create a custom category for a user."""
    cat = Category(
        user_id=user_id,
        name=name,
        parent_id=parent_id,
        icon=icon,
        is_system=False,
    )
    db.add(cat)
    await db.flush()

    await audit_service.log_event(
        db,
        user_id=user_id,
        event_type="category.created",
        entity_type="Category",
        entity_id=cat.id,
        action="create",
        detail={"name": name},
        ip_address=ip_address,
    )

    return cat
