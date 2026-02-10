import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import Connection, ConnectionStatus
from app.models.user import User


async def _create_user(db: AsyncSession) -> User:
    user = User(email="conn@example.com", password_hash="fakehash")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_connection(db_session: AsyncSession):
    user = await _create_user(db_session)
    conn = Connection(
        user_id=user.id,
        provider="plaid",
        provider_connection_id="conn_abc123",
        status=ConnectionStatus.active,
    )
    db_session.add(conn)
    await db_session.commit()

    result = await db_session.execute(select(Connection).where(Connection.user_id == user.id))
    fetched = result.scalar_one()
    assert fetched.provider == "plaid"
    assert fetched.status == ConnectionStatus.active


@pytest.mark.asyncio
async def test_connection_fk_to_user(db_session: AsyncSession):
    conn = Connection(
        user_id=uuid.uuid4(),
        provider="plaid",
        provider_connection_id="conn_bad",
    )
    db_session.add(conn)
    with pytest.raises(IntegrityError):
        await db_session.commit()
