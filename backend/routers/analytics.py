from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Numeric, func
from sqlalchemy.orm import Session

from backend.auth import get_current_user, require_admin
from backend.schemas import ActivityPoint, AnalyticsOverview, TrendPoint
from backend.services.cache import cache_service
from database.database import get_sync_db
from database.models import Consultation, MoodLog, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _date_key(value) -> str:
    """Normalize SQLite strings and PostgreSQL date objects for response maps."""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@router.get("/overview", response_model=AnalyticsOverview)
def get_overview(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Return the current user's personal dashboard summary."""
    cache_key = f"analytics:overview:user:{current_user.id}"
    cached = cache_service.get_json(cache_key)
    if cached:
        return AnalyticsOverview(**cached)

    total_mood_logs = db.query(func.count(MoodLog.id)).filter(MoodLog.user_id == current_user.id).scalar() or 0
    total_consultations = db.query(func.count(Consultation.id)).filter(Consultation.user_id == current_user.id).scalar() or 0
    avg_mood = db.query(func.avg(MoodLog.score)).filter(MoodLog.user_id == current_user.id).scalar() or 0.0

    result = AnalyticsOverview(
        total_users=1,
        total_mood_logs=total_mood_logs,
        total_consultations=total_consultations,
        avg_mood_score=round(avg_mood, 1),
    )
    cache_service.set_json(cache_key, result.model_dump(), ttl_seconds=30)
    return result


@router.get("/mood-forecast")
def get_mood_forecast(
    days: int = Query(default=7, ge=3, le=14),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Use a transparent linear trend baseline to forecast the current user's mood."""
    cache_key = f"analytics:mood-forecast:{current_user.id}:{days}"
    cached = cache_service.get_json(cache_key)
    if cached:
        return cached

    rows = (
        db.query(MoodLog)
        .filter(MoodLog.user_id == current_user.id)
        .order_by(MoodLog.created_at.desc())
        .limit(30)
        .all()
    )
    scores = [float(row.score) for row in reversed(rows)]
    if not scores:
        result = {"trend": "insufficient_data", "confidence": 0.0, "points": [], "sample_size": 0}
        cache_service.set_json(cache_key, result, 300)
        return result

    n = len(scores)
    x_mean = (n - 1) / 2
    y_mean = sum(scores) / n
    denominator = sum((index - x_mean) ** 2 for index in range(n))
    slope = sum((index - x_mean) * (score - y_mean) for index, score in enumerate(scores)) / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    residual = sum((score - (intercept + slope * index)) ** 2 for index, score in enumerate(scores)) / n
    confidence = min(0.9, max(0.15, (n / 14) * (1 / (1 + residual)))) if n >= 3 else 0.15
    today = datetime.utcnow().date()
    points = [
        {
            "date": (today + timedelta(days=offset)).isoformat(),
            "predicted_score": round(min(10.0, max(1.0, intercept + slope * (n - 1 + offset))), 1),
        }
        for offset in range(1, days + 1)
    ]
    result = {
        "trend": "improving" if slope > 0.08 else "declining" if slope < -0.08 else "stable",
        "confidence": round(confidence, 2),
        "points": points,
        "sample_size": n,
        "model": "linear_regression_baseline",
        "disclaimer": "Trend forecasting is for self-observation only and is not a medical diagnosis.",
    }
    cache_service.set_json(cache_key, result, 300)
    return result


@router.get("/mood-trend", response_model=list[TrendPoint])
def get_mood_trend(
    days: int = Query(default=14, ge=1, le=90),
    scope: str = Query(default="mine", pattern=r"^(all|mine)$"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Return personal trend by default; all-user trend is admin-only."""
    if scope == "all" and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can view all-user mood trends")

    cutoff_date = datetime.utcnow().date() - timedelta(days=days - 1)
    query = db.query(
        func.date(MoodLog.created_at).label("date"),
        # PostgreSQL only accepts the two-argument round() overload for
        # numeric, whereas avg(integer) returns double precision.
        func.round(func.avg(MoodLog.score).cast(Numeric), 1).label("avg_score"),
        func.count(MoodLog.id).label("count"),
    ).filter(func.date(MoodLog.created_at) >= cutoff_date.isoformat())
    if scope == "mine":
        query = query.filter(MoodLog.user_id == current_user.id)

    rows = (
        query.group_by(func.date(MoodLog.created_at))
        .order_by(func.date(MoodLog.created_at))
        .all()
    )
    result_map = {_date_key(r.date): (float(r.avg_score), int(r.count)) for r in rows}
    result = []
    for index in range(days):
        day = cutoff_date + timedelta(days=index)
        day_string = day.isoformat()
        point = result_map.get(day_string)
        result.append(
            TrendPoint(
                date=day_string,
                avg_score=point[0] if point else None,
                count=point[1] if point else 0,
            )
        )
    return result


@router.get("/consultation-stats", response_model=list[TrendPoint])
def get_consultation_stats(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """Return all-user consultation stats for the admin workspace."""
    cutoff_date = datetime.utcnow().date() - timedelta(days=days - 1)
    rows = (
        db.query(
            func.date(Consultation.created_at).label("date"),
            func.count(Consultation.id).label("count"),
            func.count(func.distinct(Consultation.user_id)).label("user_count"),
        )
        .filter(func.date(Consultation.created_at) >= cutoff_date.isoformat())
        .group_by(func.date(Consultation.created_at))
        .order_by("date")
        .all()
    )

    count_map = {_date_key(row.date): row.count for row in rows}
    user_map = {_date_key(row.date): row.user_count for row in rows}
    result = []
    for index in range(days):
        day = cutoff_date + timedelta(days=index)
        day_string = day.isoformat()
        result.append(
            TrendPoint(
                date=day_string,
                avg_score=None,
                count=count_map.get(day_string, 0),
                user_count=user_map.get(day_string, 0),
            )
        )
    return result


@router.get("/user-activity", response_model=list[ActivityPoint])
def get_user_activity(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    """Return all-user activity stats for the admin workspace."""
    cutoff_date = datetime.utcnow().date() - timedelta(days=days - 1)

    mood_day = (
        db.query(
            func.date(MoodLog.created_at).label("date"),
            func.count(func.distinct(MoodLog.user_id)).label("diary_users"),
        )
        .filter(func.date(MoodLog.created_at) >= cutoff_date.isoformat())
        .group_by(func.date(MoodLog.created_at))
        .all()
    )
    cons_day = (
        db.query(
            func.date(Consultation.created_at).label("date"),
            func.count(func.distinct(Consultation.user_id)).label("cons_users"),
        )
        .filter(func.date(Consultation.created_at) >= cutoff_date.isoformat())
        .group_by(func.date(Consultation.created_at))
        .all()
    )
    new_day = (
        db.query(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("new_users"),
        )
        .filter(func.date(User.created_at) >= cutoff_date.isoformat())
        .group_by(func.date(User.created_at))
        .all()
    )

    diary_map = {_date_key(row.date): row.diary_users for row in mood_day}
    cons_map = {_date_key(row.date): row.cons_users for row in cons_day}
    new_map = {_date_key(row.date): row.new_users for row in new_day}

    mood_uid_day = {}
    for row in mood_day:
        uid_rows = (
            db.query(MoodLog.user_id)
            .filter(func.date(MoodLog.created_at) == row.date)
            .distinct()
            .all()
        )
        mood_uid_day[_date_key(row.date)] = {uid_row[0] for uid_row in uid_rows}

    cons_uid_day = {}
    for row in cons_day:
        uid_rows = (
            db.query(Consultation.user_id)
            .filter(func.date(Consultation.created_at) == row.date)
            .distinct()
            .all()
        )
        cons_uid_day[_date_key(row.date)] = {uid_row[0] for uid_row in uid_rows}

    result = []
    for index in range(days):
        day = cutoff_date + timedelta(days=index)
        day_string = day.isoformat()
        mood_set = mood_uid_day.get(day_string, set())
        cons_set = cons_uid_day.get(day_string, set())
        result.append(
            ActivityPoint(
                date=day_string,
                active_users=len(mood_set | cons_set),
                new_users=new_map.get(day_string, 0),
                diary_users=diary_map.get(day_string, 0),
                consultation_users=cons_map.get(day_string, 0),
            )
        )
    return result
