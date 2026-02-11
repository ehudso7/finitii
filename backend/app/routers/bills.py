"""Bills router: derived views over RecurringPattern.

Endpoints:
- GET /bills: List all bills/subscriptions
- GET /bills/summary: Bill summary with monthly totals
- GET /bills/{bill_id}: Get a single bill
- POST /bills: Create a manual bill
- PUT /bills/{bill_id}: Update a bill
- POST /bills/{bill_id}/essential: Toggle essential flag
- DELETE /bills/{bill_id}: Deactivate a bill
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.bill import (
    BillRead,
    BillSummaryRead,
    CreateManualBillRequest,
    ToggleEssentialRequest,
    UpdateBillRequest,
)
from app.services import bill_service

router = APIRouter(prefix="/bills", tags=["bills"])


@router.get("", response_model=list[BillRead])
async def list_bills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all active bills/subscriptions.

    Bills are derived views over RecurringPattern.
    Confidence is always visible on every bill.
    """
    bills = await bill_service.get_bills(db, current_user.id)
    return bills


@router.get("/summary", response_model=BillSummaryRead)
async def get_bill_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get bill summary: total monthly cost, confidence breakdown, counts."""
    summary = await bill_service.get_bill_summary(db, current_user.id)
    return summary


@router.get("/{bill_id}", response_model=BillRead)
async def get_bill(
    bill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single bill by ID."""
    try:
        bill = await bill_service.get_bill(db, bill_id, current_user.id)
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@router.post("", response_model=BillRead, status_code=201)
async def create_manual_bill(
    body: CreateManualBillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a manual bill.

    Manual bills feed into forecast and safe-to-spend calculations.
    Manual bills have high confidence (user explicitly stated them).
    """
    try:
        bill = await bill_service.create_manual_bill(
            db,
            user_id=current_user.id,
            label=body.label,
            estimated_amount=body.estimated_amount,
            frequency=body.frequency,
            next_expected_date=body.next_expected_date,
            is_essential=body.is_essential,
            category_id=body.category_id,
        )
        await db.commit()
        return bill
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{bill_id}", response_model=BillRead)
async def update_bill(
    bill_id: uuid.UUID,
    body: UpdateBillRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a bill's fields."""
    try:
        bill = await bill_service.update_bill(
            db,
            bill_id=bill_id,
            user_id=current_user.id,
            label=body.label,
            estimated_amount=body.estimated_amount,
            frequency=body.frequency,
            next_expected_date=body.next_expected_date,
            is_essential=body.is_essential,
        )
        await db.commit()
        return bill
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Bill not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{bill_id}/essential", response_model=BillRead)
async def toggle_essential(
    bill_id: uuid.UUID,
    body: ToggleEssentialRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle the essential flag on a bill.

    Essential bills are suppressed from cancellation recommendations.
    """
    try:
        bill = await bill_service.toggle_essential(
            db,
            bill_id=bill_id,
            user_id=current_user.id,
            is_essential=body.is_essential,
        )
        await db.commit()
        return bill
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Bill not found")


@router.delete("/{bill_id}", response_model=BillRead)
async def deactivate_bill(
    bill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivate a bill (soft-delete).

    Removes from forecast calculations and bill list.
    """
    try:
        bill = await bill_service.deactivate_bill(
            db,
            bill_id=bill_id,
            user_id=current_user.id,
        )
        await db.commit()
        return bill
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Bill not found")
