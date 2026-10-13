"""Pydantic schemas for dashboard endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ProviderBreakdown(BaseModel):
    provider: str = ""
    requests: int = 0
    cost_usd: float = 0.0
    tokens_used: int = 0


class TodayMetrics(BaseModel):
    videos_processed: int = 0
    ai_requests: int = 0
    active_users: int = 0
    total_cost_usd: float = 0.0
    providers: list[ProviderBreakdown] = []


class MonthMetrics(BaseModel):
    videos_processed: int = 0
    ai_requests: int = 0
    active_users: int = 0
    total_cost_usd: float = 0.0
    providers: list[ProviderBreakdown] = []


class Trends(BaseModel):
    videos_growth_percent: float = 0.0
    users_growth_percent: float = 0.0


class TopEndpoint(BaseModel):
    endpoint: str = ""
    requests: int = 0
    cost_usd: float = 0.0


class TopUser(BaseModel):
    user_id: str = ""
    name: str = ""
    requests: int = 0
    cost_usd: float = 0.0


class RecentActivity(BaseModel):
    id: int = 0
    user_id: str = ""
    user_name: str = ""
    endpoint: str = ""
    ai_provider: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    timestamp: str | None = None


class DailyChartPoint(BaseModel):
    date: str = ""
    requests: int = 0
    cost_usd: float = 0.0
    active_users: int = 0


class DashboardOverviewResponse(BaseModel):
    today: TodayMetrics
    month: MonthMetrics
    trends: Trends
    top_endpoints: list[TopEndpoint] = []
    top_users: list[TopUser] = []
    recent_activity: list[RecentActivity] = []
    daily_chart: list[DailyChartPoint] = []
