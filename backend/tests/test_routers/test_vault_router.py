"""Phase 8 router tests: /vault endpoints."""

import io
import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storage import InMemoryStorageBackend, set_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    """Use in-memory storage for all vault router tests."""
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield backend
    set_storage(None)


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "vaultrouter@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "vaultrouter@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}


async def _upload_file(
    client: AsyncClient,
    headers: dict,
    filename: str = "receipt.jpg",
    content_type: str = "image/jpeg",
    data: bytes = b"fake image",
    item_type: str = "receipt",
) -> dict:
    """Helper to upload a file."""
    files = {"file": (filename, io.BytesIO(data), content_type)}
    form_data = {"item_type": item_type}
    resp = await client.post(
        "/vault", headers=headers, files=files, data=form_data,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_upload(client: AsyncClient, db_session: AsyncSession):
    """POST /vault uploads a file."""
    headers = await _register_and_login(client)
    data = await _upload_file(client, headers)
    assert data["filename"] == "receipt.jpg"
    assert data["content_type"] == "image/jpeg"
    assert data["item_type"] == "receipt"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient, db_session: AsyncSession):
    """POST /vault with item_type=document."""
    headers = await _register_and_login(client)
    data = await _upload_file(
        client, headers,
        filename="statement.pdf",
        content_type="application/pdf",
        data=b"pdf content",
        item_type="document",
    )
    assert data["item_type"] == "document"


@pytest.mark.asyncio
async def test_upload_invalid_type(client: AsyncClient, db_session: AsyncSession):
    """POST /vault rejects unsupported content types."""
    headers = await _register_and_login(client)
    files = {"file": ("script.js", io.BytesIO(b"alert(1)"), "application/javascript")}
    resp = await client.post(
        "/vault", headers=headers, files=files, data={"item_type": "receipt"},
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_items(client: AsyncClient, db_session: AsyncSession):
    """GET /vault lists uploaded items."""
    headers = await _register_and_login(client)
    await _upload_file(client, headers, filename="f1.jpg")
    await _upload_file(client, headers, filename="f2.jpg")

    resp = await client.get("/vault", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_items_filter_type(client: AsyncClient, db_session: AsyncSession):
    """GET /vault?item_type=receipt filters."""
    headers = await _register_and_login(client)
    await _upload_file(client, headers, item_type="receipt")
    await _upload_file(
        client, headers, filename="doc.pdf",
        content_type="application/pdf", data=b"pdf", item_type="document",
    )

    resp = await client.get("/vault?item_type=receipt", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["item_type"] == "receipt"


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient, db_session: AsyncSession):
    """GET /vault/{id} returns item metadata."""
    headers = await _register_and_login(client)
    uploaded = await _upload_file(client, headers)
    item_id = uploaded["id"]

    resp = await client.get(f"/vault/{item_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == item_id


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient, db_session: AsyncSession):
    """GET /vault/{invalid} returns 404."""
    headers = await _register_and_login(client)
    resp = await client.get(
        "/vault/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_file(client: AsyncClient, db_session: AsyncSession):
    """GET /vault/{id}/download returns file bytes."""
    headers = await _register_and_login(client)
    uploaded = await _upload_file(
        client, headers, data=b"real file content"
    )
    item_id = uploaded["id"]

    resp = await client.get(f"/vault/{item_id}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"real file content"
    assert resp.headers["content-type"] == "image/jpeg"
    assert "attachment" in resp.headers["content-disposition"]


async def _create_transaction(db_session: AsyncSession, user_id: uuid.UUID) -> str:
    """Create a real transaction for FK-safe linking tests."""
    from sqlalchemy import select
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    account = Account(
        user_id=user_id, institution_name="Bank", account_name="Check",
        account_type="checking", currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        account_id=account.id, user_id=user_id,
        raw_description="Test", normalized_description="test",
        amount=25.00, transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()
    return str(txn.id)


async def _get_user_id(db_session: AsyncSession, email: str) -> uuid.UUID:
    """Get user ID from email."""
    from sqlalchemy import select
    from app.models.user import User
    result = await db_session.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one().id


@pytest.mark.asyncio
async def test_link_transaction(client: AsyncClient, db_session: AsyncSession):
    """POST /vault/{id}/link-transaction links item to transaction."""
    headers = await _register_and_login(client)
    uploaded = await _upload_file(client, headers)
    item_id = uploaded["id"]

    user_id = await _get_user_id(db_session, "vaultrouter@test.com")
    txn_id = await _create_transaction(db_session, user_id)

    resp = await client.post(
        f"/vault/{item_id}/link-transaction",
        json={"transaction_id": txn_id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["transaction_id"] == txn_id


@pytest.mark.asyncio
async def test_unlink_transaction(client: AsyncClient, db_session: AsyncSession):
    """POST /vault/{id}/unlink-transaction removes link."""
    headers = await _register_and_login(client)
    uploaded = await _upload_file(client, headers)
    item_id = uploaded["id"]

    user_id = await _get_user_id(db_session, "vaultrouter@test.com")
    txn_id = await _create_transaction(db_session, user_id)

    await client.post(
        f"/vault/{item_id}/link-transaction",
        json={"transaction_id": txn_id},
        headers=headers,
    )

    resp = await client.post(
        f"/vault/{item_id}/unlink-transaction", headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["transaction_id"] is None


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient, db_session: AsyncSession):
    """DELETE /vault/{id} removes item."""
    headers = await _register_and_login(client)
    uploaded = await _upload_file(client, headers)
    item_id = uploaded["id"]

    resp = await client.delete(f"/vault/{item_id}", headers=headers)
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get(f"/vault/{item_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_found(client: AsyncClient, db_session: AsyncSession):
    """DELETE /vault/{invalid} returns 404."""
    headers = await _register_and_login(client)
    resp = await client.delete(
        "/vault/00000000-0000-0000-0000-000000000000", headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient):
    """Vault endpoints require authentication."""
    resp = await client.get("/vault")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_with_description(client: AsyncClient, db_session: AsyncSession):
    """POST /vault with description field."""
    headers = await _register_and_login(client)
    files = {"file": ("receipt.jpg", io.BytesIO(b"data"), "image/jpeg")}
    form_data = {"item_type": "receipt", "description": "Dinner at Luigi's"}
    resp = await client.post(
        "/vault", headers=headers, files=files, data=form_data,
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "Dinner at Luigi's"
