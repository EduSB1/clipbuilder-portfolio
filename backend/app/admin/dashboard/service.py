"""Dashboard metrics aggregation service."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.admin.models import ApiUsageLog, User
from app.core.constants import (
    DASHBOARD_CHART_DAYS,
    END_OF_DAY_HOUR,
    END_OF_DAY_MINUTE,
    END_OF_DAY_SECOND,
    RECENT_ACTIVITY_LOG_LIMIT,
)


def get_dashboard_overview(db: Session) -> dict:
    """Aggregate metrics for today, month, and trends."""
    now = datetime.now(UTC)
    today = now.date()
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start - timedelta(days=1)

    # Today: count unique users with activity, total AI requests, cost
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    today_logs = db.execute(
        select(
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
            func.count(func.distinct(ApiUsageLog.user_id)).label("users"),
        ).where(ApiUsageLog.timestamp >= today_start)
    ).one_or_none() or (0, Decimal("0"), 0)
    today_requests = today_logs[0] or 0
    today_cost = float(today_logs[1] or 0)
    today_active = today_logs[2] or 0

    # Month: same logic
    month_start_dt = datetime(
        month_start.year, month_start.month, month_start.day, tzinfo=UTC
    )
    month_logs = db.execute(
        select(
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
            func.count(func.distinct(ApiUsageLog.user_id)).label("users"),
        ).where(ApiUsageLog.timestamp >= month_start_dt)
    ).one_or_none() or (0, Decimal("0"), 0)
    month_requests = month_logs[0] or 0
    month_cost = float(month_logs[1] or 0)
    month_active = month_logs[2] or 0

    # Vídeos processados: ainda não há tabela própria, então o total de
    # requisições de IA é usado como proxy.
    today_videos = today_requests  # placeholder
    month_videos = month_requests  # placeholder

    # Trends: compare with last month
    last_month_start_dt = datetime(
        last_month_start.year,
        last_month_start.month,
        last_month_start.day,
        tzinfo=UTC,
    )
    last_month_end_dt = datetime(
        last_month_end.year,
        last_month_end.month,
        last_month_end.day,
        END_OF_DAY_HOUR,
        END_OF_DAY_MINUTE,
        END_OF_DAY_SECOND,
        tzinfo=UTC,
    )
    last_month_requests = (
        db.scalar(
            select(func.count(ApiUsageLog.id)).where(
                ApiUsageLog.timestamp >= last_month_start_dt,
                ApiUsageLog.timestamp <= last_month_end_dt,
            )
        )
        or 0
    )
    last_month_users = (
        db.scalar(
            select(func.count(func.distinct(ApiUsageLog.user_id))).where(
                ApiUsageLog.timestamp >= last_month_start_dt,
                ApiUsageLog.timestamp <= last_month_end_dt,
            )
        )
        or 0
    )

    videos_growth = 0.0
    if last_month_requests > 0:
        videos_growth = round(
            ((month_requests - last_month_requests) / last_month_requests) * 100, 1
        )
    users_growth = 0.0
    if last_month_users > 0:
        users_growth = round(
            ((month_active - last_month_users) / last_month_users) * 100, 1
        )

    # ── Per-provider breakdown (month) ──────────────────────────────────────
    provider_rows = db.execute(
        select(
            ApiUsageLog.ai_provider,
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
            func.coalesce(func.sum(ApiUsageLog.tokens_used), 0).label("tokens"),
        )
        .where(ApiUsageLog.timestamp >= month_start_dt)
        .group_by(ApiUsageLog.ai_provider)
        .order_by(desc("requests"))
    ).all()

    providers_breakdown = []
    for row in provider_rows:
        providers_breakdown.append(
            {
                "provider": row[0] or "unknown",
                "requests": row[1] or 0,
                "cost_usd": round(float(row[2] or 0), 4),
                "tokens_used": row[3] or 0,
            }
        )

    # Today per-provider
    today_provider_rows = db.execute(
        select(
            ApiUsageLog.ai_provider,
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
            func.coalesce(func.sum(ApiUsageLog.tokens_used), 0).label("tokens"),
        )
        .where(ApiUsageLog.timestamp >= today_start)
        .group_by(ApiUsageLog.ai_provider)
        .order_by(desc("requests"))
    ).all()

    today_providers_breakdown = []
    for row in today_provider_rows:
        today_providers_breakdown.append(
            {
                "provider": row[0] or "unknown",
                "requests": row[1] or 0,
                "cost_usd": round(float(row[2] or 0), 4),
                "tokens_used": row[3] or 0,
            }
        )

    # ── Top endpoints (month) ───────────────────────────────────────────────
    endpoint_rows = db.execute(
        select(
            ApiUsageLog.endpoint,
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
        )
        .where(ApiUsageLog.timestamp >= month_start_dt)
        .group_by(ApiUsageLog.endpoint)
        .order_by(desc("requests"))
        .limit(10)
    ).all()

    top_endpoints = []
    for row in endpoint_rows:
        top_endpoints.append(
            {
                "endpoint": row[0] or "unknown",
                "requests": row[1] or 0,
                "cost_usd": round(float(row[2] or 0), 4),
            }
        )

    # ── Top users (month) ──────────────────────────────────────────────────
    top_user_rows = db.execute(
        select(
            ApiUsageLog.user_id,
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
        )
        .where(ApiUsageLog.timestamp >= month_start_dt)
        .group_by(ApiUsageLog.user_id)
        .order_by(desc("requests"))
        .limit(10)
    ).all()

    # Enrich with user names
    top_users = []
    user_ids = [row[0] for row in top_user_rows if row[0]]
    user_name_map: dict[str, str] = {}
    if user_ids:
        name_rows = db.execute(
            select(User.id, User.full_name, User.email).where(User.id.in_(user_ids))
        ).all()
        for nr in name_rows:
            user_name_map[nr[0]] = nr[1] or nr[2] or nr[0]

    for row in top_user_rows:
        uid = row[0] or "unknown"
        top_users.append(
            {
                "user_id": uid,
                "name": user_name_map.get(uid, uid),
                "requests": row[1] or 0,
                "cost_usd": round(float(row[2] or 0), 4),
            }
        )

    # ── Recent activity (last 20 logs) ─────────────────────────────────────
    recent_rows = db.execute(
        select(
            ApiUsageLog.id,
            ApiUsageLog.user_id,
            ApiUsageLog.endpoint,
            ApiUsageLog.ai_provider,
            ApiUsageLog.tokens_used,
            ApiUsageLog.cost_usd,
            ApiUsageLog.timestamp,
        )
        .order_by(desc(ApiUsageLog.timestamp))
        .limit(RECENT_ACTIVITY_LOG_LIMIT)
    ).all()

    recent_activity = []
    # Gather user names for recent rows
    recent_user_ids = list({row[1] for row in recent_rows if row[1]})
    recent_user_map: dict[str, str] = {}
    if recent_user_ids:
        rn_rows = db.execute(
            select(User.id, User.full_name, User.email).where(
                User.id.in_(recent_user_ids)
            )
        ).all()
        for rn in rn_rows:
            recent_user_map[rn[0]] = rn[1] or rn[2] or rn[0]

    for row in recent_rows:
        uid = row[1] or "unknown"
        recent_activity.append(
            {
                "id": row[0],
                "user_id": uid,
                "user_name": recent_user_map.get(uid, uid),
                "endpoint": row[2] or "",
                "ai_provider": row[3] or "",
                "tokens_used": row[4] or 0,
                "cost_usd": round(float(row[5] or 0), 4),
                "timestamp": row[6].isoformat() if row[6] else None,
            }
        )

    # ── Daily chart data (last 30 days) ────────────────────────────────────
    thirty_days_ago = datetime(
        (today - timedelta(days=DASHBOARD_CHART_DAYS)).year,
        (today - timedelta(days=DASHBOARD_CHART_DAYS)).month,
        (today - timedelta(days=DASHBOARD_CHART_DAYS)).day,
        tzinfo=UTC,
    )

    daily_rows = db.execute(
        select(
            func.date(ApiUsageLog.timestamp).label("day"),
            func.count(ApiUsageLog.id).label("requests"),
            func.coalesce(func.sum(ApiUsageLog.cost_usd), 0).label("cost"),
            func.count(func.distinct(ApiUsageLog.user_id)).label("users"),
        )
        .where(ApiUsageLog.timestamp >= thirty_days_ago)
        .group_by(func.date(ApiUsageLog.timestamp))
        .order_by(func.date(ApiUsageLog.timestamp))
    ).all()

    daily_chart = []
    for row in daily_rows:
        day_val = row[0]
        if isinstance(day_val, str):
            day_str = day_val
        elif isinstance(day_val, date):
            day_str = day_val.isoformat()
        else:
            day_str = str(day_val)
        daily_chart.append(
            {
                "date": day_str,
                "requests": row[1] or 0,
                "cost_usd": round(float(row[2] or 0), 4),
                "active_users": row[3] or 0,
            }
        )

    return {
        "today": {
            "videos_processed": today_videos,
            "ai_requests": today_requests,
            "active_users": today_active,
            "total_cost_usd": round(today_cost, 2),
            "providers": today_providers_breakdown,
        },
        "month": {
            "videos_processed": month_videos,
            "ai_requests": month_requests,
            "active_users": month_active,
            "total_cost_usd": round(month_cost, 2),
            "providers": providers_breakdown,
        },
        "trends": {
            "videos_growth_percent": videos_growth,
            "users_growth_percent": users_growth,
        },
        "top_endpoints": top_endpoints,
        "top_users": top_users,
        "recent_activity": recent_activity,
        "daily_chart": daily_chart,
    }
