"""User routes: export, delete."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.services import delete_service, export_service

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/export")
async def export_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    data = await export_service.export_user_data(db, current_user.id, ip_address=ip)
    return data


@router.delete("/delete", status_code=204)
async def delete_account(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    await delete_service.delete_user_data(db, current_user.id, ip_address=ip)
