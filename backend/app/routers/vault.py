"""Vault routes: upload, list, download, link-to-transaction, delete.

Phase 8: Vault — receipts & documents lite.

Files are served only through authenticated endpoints (no public access).
"""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.vault import LinkTransactionRequest, VaultItemRead
from app.services import vault_service

router = APIRouter(prefix="/vault", tags=["vault"])


@router.post("", response_model=VaultItemRead, status_code=201)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    item_type: str = Form("receipt"),
    description: str | None = Form(None),
    transaction_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a receipt or document to the vault."""
    ip = request.client.host if request.client else None

    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unnamed"

    txn_id = None
    if transaction_id:
        try:
            txn_id = uuid_mod.UUID(transaction_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transaction_id")

    try:
        item = await vault_service.upload(
            db,
            user_id=current_user.id,
            filename=filename,
            content_type=content_type,
            data=data,
            item_type=item_type,
            description=description,
            transaction_id=txn_id,
            ip_address=ip,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return VaultItemRead.model_validate(item)


@router.get("", response_model=list[VaultItemRead])
async def list_items(
    item_type: str | None = None,
    transaction_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List vault items for the current user."""
    txn_id = None
    if transaction_id:
        try:
            txn_id = uuid_mod.UUID(transaction_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid transaction_id")

    items = await vault_service.list_items(
        db, user_id=current_user.id, item_type=item_type, transaction_id=txn_id
    )
    return [VaultItemRead.model_validate(i) for i in items]


@router.get("/{item_id}", response_model=VaultItemRead)
async def get_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get vault item metadata."""
    try:
        iid = uuid_mod.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")
    try:
        item = await vault_service.get_item(db, item_id=iid, user_id=current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Vault item not found")
    return VaultItemRead.model_validate(item)


@router.get("/{item_id}/download")
async def download_file(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download vault file (authenticated access only)."""
    try:
        iid = uuid_mod.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")
    try:
        item, data = await vault_service.get_file_data(
            db, item_id=iid, user_id=current_user.id
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Vault item not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found in storage")

    return Response(
        content=data,
        media_type=item.content_type,
        headers={"Content-Disposition": f'attachment; filename="{item.filename}"'},
    )


@router.post("/{item_id}/link-transaction", response_model=VaultItemRead)
async def link_transaction(
    item_id: str,
    body: LinkTransactionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a vault item to a transaction."""
    ip = request.client.host if request.client else None
    try:
        iid = uuid_mod.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")
    try:
        txn_id = uuid_mod.UUID(body.transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction_id")
    try:
        item = await vault_service.link_to_transaction(
            db, item_id=iid, user_id=current_user.id,
            transaction_id=txn_id, ip_address=ip,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Vault item not found")
    return VaultItemRead.model_validate(item)


@router.post("/{item_id}/unlink-transaction", response_model=VaultItemRead)
async def unlink_transaction(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink a vault item from its transaction."""
    ip = request.client.host if request.client else None
    try:
        iid = uuid_mod.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")
    try:
        item = await vault_service.unlink_transaction(
            db, item_id=iid, user_id=current_user.id, ip_address=ip,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Vault item not found")
    return VaultItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a vault item (DB row + storage file)."""
    ip = request.client.host if request.client else None
    try:
        iid = uuid_mod.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")
    try:
        await vault_service.delete_item(
            db, item_id=iid, user_id=current_user.id, ip_address=ip,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Vault item not found")
