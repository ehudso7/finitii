"""Account routes: list, create manual, update balance. Returns derived views."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.derived_views.money_graph import account_summary_view
from app.models.account import AccountType
from app.models.user import User
from app.schemas.account import AccountBalanceUpdate, AccountCreate
from app.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _parse_account_type(value: str) -> AccountType:
    try:
        return AccountType(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid account_type: {value}",
        )


@router.get("")
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await account_summary_view(db, current_user.id)


@router.post("/manual", status_code=201)
async def create_manual(
    body: AccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    acct_type = _parse_account_type(body.account_type)
    acct = await account_service.create_manual_account(
        db,
        user_id=current_user.id,
        account_type=acct_type,
        institution_name=body.institution_name,
        account_name=body.account_name,
        current_balance=body.current_balance,
        available_balance=body.available_balance,
        currency=body.currency,
        ip_address=ip,
    )
    # Return the derived view for this account
    views = await account_summary_view(db, current_user.id)
    return [v for v in views if v["id"] == str(acct.id)][0]


@router.patch("/{account_id}/balance")
async def update_balance(
    account_id: str,
    body: AccountBalanceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import uuid as uuid_mod

    ip = request.client.host if request.client else None
    try:
        aid = uuid_mod.UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account_id")

    await account_service.update_manual_balance(
        db,
        account_id=aid,
        new_balance=body.current_balance,
        user_id=current_user.id,
        available_balance=body.available_balance,
        ip_address=ip,
    )
    views = await account_summary_view(db, current_user.id)
    return [v for v in views if v["id"] == account_id][0]
