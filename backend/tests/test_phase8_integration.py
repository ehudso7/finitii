"""Phase 8 integration test: full vault flow through API."""

import io
import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storage import InMemoryStorageBackend, set_storage, get_storage


@pytest.fixture(autouse=True)
def _use_in_memory_storage():
    """Use in-memory storage for all integration tests."""
    backend = InMemoryStorageBackend()
    set_storage(backend)
    yield backend
    set_storage(None)


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "p8integ@test.com", "password": "SecurePass123!"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "p8integ@test.com", "password": "SecurePass123!"},
    )
    data = resp.json()
    return {"X-Session-Token": data["token"]}


@pytest.mark.asyncio
async def test_full_vault_flow(client: AsyncClient, db_session: AsyncSession):
    """E2E: upload → list → get → download → link → unlink → delete."""
    headers = await _register_and_login(client)

    # 1. Upload a receipt
    files = {"file": ("lunch_receipt.jpg", io.BytesIO(b"JPEG content here"), "image/jpeg")}
    form_data = {"item_type": "receipt", "description": "Business lunch"}
    resp = await client.post("/vault", headers=headers, files=files, data=form_data)
    assert resp.status_code == 201
    item = resp.json()
    item_id = item["id"]
    assert item["filename"] == "lunch_receipt.jpg"
    assert item["description"] == "Business lunch"
    assert item["item_type"] == "receipt"
    assert item["file_size"] == len(b"JPEG content here")

    # 2. Upload a document
    files2 = {"file": ("statement.pdf", io.BytesIO(b"PDF content"), "application/pdf")}
    resp = await client.post(
        "/vault", headers=headers, files=files2,
        data={"item_type": "document"},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # 3. List — should see both
    resp = await client.get("/vault", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # 4. Filter by type
    resp = await client.get("/vault?item_type=document", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["item_type"] == "document"

    # 5. Get specific item
    resp = await client.get(f"/vault/{item_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["filename"] == "lunch_receipt.jpg"

    # 6. Download file
    resp = await client.get(f"/vault/{item_id}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.content == b"JPEG content here"
    assert "attachment" in resp.headers["content-disposition"]
    assert "lunch_receipt.jpg" in resp.headers["content-disposition"]

    # 7. Create a real transaction to link to
    from sqlalchemy import select
    from app.models.user import User
    from app.models.account import Account
    from app.models.transaction import Transaction, TransactionType

    user_result = await db_session.execute(
        select(User).where(User.email == "p8integ@test.com")
    )
    user = user_result.scalar_one()
    account = Account(
        user_id=user.id, institution_name="Bank", account_name="Check",
        account_type="checking", currency="USD",
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        account_id=account.id, user_id=user.id,
        raw_description="Lunch", normalized_description="lunch",
        amount=25.00, transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.debit,
    )
    db_session.add(txn)
    await db_session.flush()
    txn_id_str = str(txn.id)

    # Link to transaction
    resp = await client.post(
        f"/vault/{item_id}/link-transaction",
        json={"transaction_id": txn_id_str},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["transaction_id"] == txn_id_str

    # 8. Verify linked in listing
    resp = await client.get(f"/vault/{item_id}", headers=headers)
    assert resp.json()["transaction_id"] == txn_id_str

    # 9. Unlink
    resp = await client.post(
        f"/vault/{item_id}/unlink-transaction", headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["transaction_id"] is None

    # 10. Delete the receipt
    resp = await client.delete(f"/vault/{item_id}", headers=headers)
    assert resp.status_code == 204

    # 11. Verify gone
    resp = await client.get(f"/vault/{item_id}", headers=headers)
    assert resp.status_code == 404

    # 12. Only document remains
    resp = await client.get("/vault", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == doc_id


@pytest.mark.asyncio
async def test_account_deletion_cleans_vault(client: AsyncClient, db_session: AsyncSession):
    """Deleting user account deletes all vault items and storage files."""
    headers = await _register_and_login(client)
    storage = get_storage()

    # Upload 2 files
    for name in ("a.jpg", "b.png"):
        ct = "image/jpeg" if name.endswith(".jpg") else "image/png"
        files = {"file": (name, io.BytesIO(b"data"), ct)}
        resp = await client.post(
            "/vault", headers=headers, files=files,
            data={"item_type": "receipt"},
        )
        assert resp.status_code == 201

    # Verify 2 items
    resp = await client.get("/vault", headers=headers)
    assert len(resp.json()) == 2

    # Delete account
    resp = await client.delete("/user/delete", headers=headers)
    assert resp.status_code == 204

    # Storage should be empty (all files cleaned up)
    assert len(storage._store) == 0
