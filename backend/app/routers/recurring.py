"""Recurring pattern routes: list, detect. Returns derived views."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.derived_views.money_graph import recurring_patterns_view
from app.models.user import User
from app.services import recurring_service

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("")
async def list_patterns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await recurring_patterns_view(db, current_user.id)


@router.post("/detect")
async def detect_patterns(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    await recurring_service.detect_patterns(db, current_user.id, ip_address=ip)
    return await recurring_patterns_view(db, current_user.id)
