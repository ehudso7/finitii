"""Money graph summary route. Returns derived view."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.dependencies import get_db
from app.derived_views.money_graph import money_graph_summary_view
from app.models.user import User

router = APIRouter(prefix="/money-graph", tags=["money-graph"])


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await money_graph_summary_view(db, current_user.id)
