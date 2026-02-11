"""Transaction routes: list, create manual, recategorize. Returns derived views."""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.derived_views.money_graph import transaction_list_view
from app.models.transaction import TransactionType
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionRecategorize
from app.services import category_service, transaction_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _parse_transaction_type(value: str) -> TransactionType:
    try:
        return TransactionType(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transaction_type: {value}",
        )


@router.get("")
async def list_transactions(
    account_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    aid = None
    if account_id:
        try:
            aid = uuid_mod.UUID(account_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid account_id")

    return await transaction_list_view(
        db, current_user.id, account_id=aid, limit=limit, offset=offset
    )


@router.post("", status_code=201)
async def create_transaction(
    body: TransactionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    txn_type = _parse_transaction_type(body.transaction_type)

    # Seed categories if needed
    await category_service.seed_system_categories(db)

    txn = await transaction_service.ingest_transaction(
        db,
        account_id=body.account_id,
        user_id=current_user.id,
        raw_description=body.raw_description,
        amount=body.amount,
        transaction_type=txn_type,
        transaction_date=body.transaction_date,
        posted_date=body.posted_date,
        is_pending=body.is_pending,
        currency=body.currency,
        category_id=body.category_id,
        ip_address=ip,
    )

    # Return as derived view
    views = await transaction_list_view(db, current_user.id, limit=1)
    if views:
        return views[0]
    return {"id": str(txn.id)}


@router.patch("/{transaction_id}/category")
async def recategorize(
    transaction_id: str,
    body: TransactionRecategorize,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    try:
        tid = uuid_mod.UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid transaction_id")

    await transaction_service.recategorize(
        db,
        transaction_id=tid,
        category_id=body.category_id,
        user_id=current_user.id,
        ip_address=ip,
    )

    views = await transaction_list_view(db, current_user.id, limit=200)
    return [v for v in views if v["id"] == transaction_id][0]
