"""Auth routes: register, login, logout."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, login_user, logout_user, register_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=201)
async def register(
    body: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    user = await register_user(db, email=body.email, password=body.password, ip_address=ip)
    return user


@router.post("/login")
async def login(
    body: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    user, token = await login_user(db, email=body.email, password=body.password, ip_address=ip)
    return {"token": token, "user_id": str(user.id)}


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token = request.headers.get("X-Session-Token")
    ip = request.client.host if request.client else None
    await logout_user(db, token=token, ip_address=ip)
