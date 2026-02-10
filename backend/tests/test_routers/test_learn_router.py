"""Phase 7 router tests: /learn endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.lesson_seed import seed_lessons


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "learnrouter@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "learnrouter@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}


@pytest.mark.asyncio
async def test_list_lessons(client: AsyncClient, db_session: AsyncSession):
    """GET /learn/lessons returns seeded lessons."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    assert resp.status_code == 200
    lessons = resp.json()
    assert len(lessons) == 10


@pytest.mark.asyncio
async def test_list_lessons_filter_category(client: AsyncClient, db_session: AsyncSession):
    """GET /learn/lessons?category=save_money filters."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons?category=save_money", headers=headers)
    assert resp.status_code == 200
    lessons = resp.json()
    assert len(lessons) == 2
    assert all(l["category"] == "save_money" for l in lessons)


@pytest.mark.asyncio
async def test_get_lesson_by_id(client: AsyncClient, db_session: AsyncSession):
    """GET /learn/lessons/{id} returns lesson details."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    lesson_id = resp.json()[0]["id"]

    resp = await client.get(f"/learn/lessons/{lesson_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == lesson_id


@pytest.mark.asyncio
async def test_get_lesson_invalid_id(client: AsyncClient, db_session: AsyncSession):
    """GET /learn/lessons/{invalid} returns 400."""
    headers = await _register_and_login(client)
    resp = await client.get("/learn/lessons/not-a-uuid", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_start_lesson(client: AsyncClient, db_session: AsyncSession):
    """POST /learn/start creates progress."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    lesson_id = resp.json()[0]["id"]

    resp = await client.post(
        "/learn/start",
        json={"lesson_id": lesson_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["completed_sections"] == 0


@pytest.mark.asyncio
async def test_complete_section(client: AsyncClient, db_session: AsyncSession):
    """POST /learn/complete-section advances progress."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    lesson_id = resp.json()[0]["id"]

    # Start lesson
    await client.post(
        "/learn/start", json={"lesson_id": lesson_id}, headers=headers,
    )

    # Complete section 1
    resp = await client.post(
        "/learn/complete-section",
        json={"lesson_id": lesson_id, "section_number": 1},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["completed_sections"] == 1


@pytest.mark.asyncio
async def test_complete_section_invalid(client: AsyncClient, db_session: AsyncSession):
    """POST /learn/complete-section with invalid section returns 400."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    lesson_id = resp.json()[0]["id"]

    await client.post(
        "/learn/start", json={"lesson_id": lesson_id}, headers=headers,
    )

    resp = await client.post(
        "/learn/complete-section",
        json={"lesson_id": lesson_id, "section_number": 99},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_progress(client: AsyncClient, db_session: AsyncSession):
    """GET /learn/progress returns user's progress."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    lesson_id = resp.json()[0]["id"]

    await client.post(
        "/learn/start", json={"lesson_id": lesson_id}, headers=headers,
    )

    resp = await client.get("/learn/progress", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_get_progress_for_lesson(client: AsyncClient, db_session: AsyncSession):
    """GET /learn/progress/{id} returns progress for specific lesson."""
    headers = await _register_and_login(client)
    await seed_lessons(db_session)

    resp = await client.get("/learn/lessons", headers=headers)
    lesson_id = resp.json()[0]["id"]

    # Before start — null
    resp = await client.get(f"/learn/progress/{lesson_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None

    # After start
    await client.post(
        "/learn/start", json={"lesson_id": lesson_id}, headers=headers,
    )
    resp = await client.get(f"/learn/progress/{lesson_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    """Learn endpoints require authentication."""
    resp = await client.get("/learn/lessons")
    assert resp.status_code in (401, 403)
