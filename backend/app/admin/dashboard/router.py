"""Dashboard API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.admin.dashboard.schemas import DashboardOverviewResponse
from app.admin.dashboard.service import get_dashboard_overview
from app.admin.dependencies import RequireAdmin
from app.database import get_db

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def dashboard_overview(
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    """Return aggregated KPIs for today, month, and trends."""
    data = get_dashboard_overview(db)
    return DashboardOverviewResponse(**data)
