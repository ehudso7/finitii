"""Forecast router: Safe-to-Spend and 30-day projection endpoints.

Endpoints:
- POST /forecast/compute: Compute a new forecast snapshot
- GET /forecast/latest: Get the most recent forecast
- GET /forecast/summary: Lightweight summary for dashboard
- GET /forecast/history: Get recent forecast history
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.models.user import User
from app.schemas.forecast import ForecastRead, ForecastSummaryRead
from app.services import forecast_service

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.post("/compute", response_model=ForecastRead, status_code=201)
async def compute_forecast(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute a new forecast snapshot.

    Returns Safe-to-Spend (today + week), 30-day daily projections
    with volatility bands, confidence, assumptions, and urgency score.
    """
    snapshot = await forecast_service.compute_forecast(db, current_user.id)
    await db.commit()
    return snapshot


@router.get("/latest", response_model=ForecastRead)
async def get_latest_forecast(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent forecast snapshot."""
    snapshot = await forecast_service.get_latest_forecast(db, current_user.id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No forecast found. Compute one first.")
    return snapshot


@router.get("/summary", response_model=ForecastSummaryRead)
async def get_forecast_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a lightweight forecast summary for the dashboard."""
    snapshot = await forecast_service.get_latest_forecast(db, current_user.id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No forecast found. Compute one first.")
    return snapshot


@router.get("/history", response_model=list[ForecastSummaryRead])
async def get_forecast_history(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent forecast history (summaries)."""
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 50")
    snapshots = await forecast_service.get_forecast_history(
        db, current_user.id, limit=limit
    )
    return snapshots
