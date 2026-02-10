"""Consent routes: grant, revoke, status."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.consent import ConsentType
from app.models.user import User
from app.schemas.consent import ConsentGrant, ConsentRecordRead, ConsentRevoke, ConsentStatus
from app.services import consent_service

router = APIRouter(prefix="/consent", tags=["consent"])


def _parse_consent_type(value: str) -> ConsentType:
    try:
        return ConsentType(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid consent_type: {value}. Must be one of: {[e.value for e in ConsentType]}",
        )


@router.post("/grant", response_model=ConsentRecordRead)
async def grant(
    body: ConsentGrant,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consent_type = _parse_consent_type(body.consent_type)
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    consent = await consent_service.grant_consent(
        db,
        user_id=current_user.id,
        consent_type=consent_type,
        ip_address=ip,
        user_agent=ua,
    )
    return consent


@router.post("/revoke", response_model=ConsentRecordRead | None)
async def revoke(
    body: ConsentRevoke,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consent_type = _parse_consent_type(body.consent_type)
    ip = request.client.host if request.client else None
    consent = await consent_service.revoke_consent(
        db,
        user_id=current_user.id,
        consent_type=consent_type,
        ip_address=ip,
    )
    if consent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active consent of this type found",
        )
    return consent


@router.get("/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consents = {}
    for ct in ConsentType:
        granted = await consent_service.check_consent(db, current_user.id, ct)
        consents[ct.value] = granted
    return {"consents": consents}
