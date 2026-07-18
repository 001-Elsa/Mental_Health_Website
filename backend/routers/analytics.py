from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.database import get_sync_db
from database.models import User, MoodLog, Consultation
from backend.auth import get_current_user, get_optional_user
from backend.services.cache import cache_service
from backend.schemas import AnalyticsOverview, TrendPoint, ActivityPoint

router = APIRouter(prefix="/api/analytics", tags=["数据分析"])


@router.get("/overview", response_model=AnalyticsOverview)
def get_overview(db: Session = Depends(get_sync_db)):
    """获取仪表盘四个核心统计数"""
    cached = cache_service.get_json("analytics:overview")
    if cached:
        return AnalyticsOverview(**cached)
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_mood_logs = db.query(func.count(MoodLog.id)).scalar() or 0
    total_consultations = db.query(func.count(Consultation.id)).scalar() or 0
    avg_mood = db.query(func.avg(MoodLog.score)).scalar() or 0.0

    result = AnalyticsOverview(
        total_users=total_users,
        total_mood_logs=total_mood_logs,
        total_consultations=total_consultations,
        avg_mood_score=round(avg_mood, 1),
    )
    cache_service.set_json("analytics:overview", result.model_dump(), ttl_seconds=30)
    return result


@router.get("/mood-forecast")
def get_mood_forecast(
    days: int = Query(default=7, ge=3, le=14),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Use a transparent linear trend baseline to forecast the next N daily mood scores."""
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
        "disclaimer": "趋势预测仅用于自我观察，不用于医疗诊断。",
    }
    cache_service.set_json(cache_key, result, 300)
    return result


@router.get("/mood-trend", response_model=list[TrendPoint])
def get_mood_trend(
    days: int = Query(default=14, ge=1, le=90),
    scope: str = Query(default="all", pattern=r"^(all|mine)$"),
    db: Session = Depends(get_sync_db),
    current_user: User | None = Depends(get_optional_user),
):
    """获取全部用户或当前用户最近 N 天的每日平均情绪评分。"""
    if scope == "mine" and current_user is None:
        raise HTTPException(status_code=401, detail="登录后才能查看个人情绪趋势")

    cutoff_date = datetime.utcnow().date() - timedelta(days=days - 1)

    query = db.query(
        func.date(MoodLog.created_at).label("date"),
        func.round(func.avg(MoodLog.score), 1).label("avg_score"),
        func.count(MoodLog.id).label("count"),
    ).filter(func.date(MoodLog.created_at) >= cutoff_date.isoformat())
    if scope == "mine" and current_user is not None:
        query = query.filter(MoodLog.user_id == current_user.id)
    rows = (
        query.group_by(func.date(MoodLog.created_at))
        .order_by(func.date(MoodLog.created_at))
        .all()
    )

    # 补全缺失日期
    result_map = {r.date: (float(r.avg_score), int(r.count)) for r in rows}
    result = []
    for i in range(days):
        d = cutoff_date + timedelta(days=i)
        ds = d.isoformat()
        point = result_map.get(ds)
        result.append(
            TrendPoint(
                date=ds,
                avg_score=point[0] if point else None,
                count=point[1] if point else 0,
            )
        )
    return result


@router.get("/consultation-stats", response_model=list[TrendPoint])
def get_consultation_stats(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_sync_db),
):
    """获取最近 N 天的每日咨询数 + 参与用户数"""
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

    count_map = {r.date: r.count for r in rows}
    user_map = {r.date: r.user_count for r in rows}
    result = []
    for i in range(days):
        d = cutoff_date + timedelta(days=i)
        ds = d.isoformat()
        result.append(
            TrendPoint(
                date=ds,
                avg_score=None,
                count=count_map.get(ds, 0),
                user_count=user_map.get(ds, 0),
            )
        )
    return result


@router.get("/user-activity", response_model=list[ActivityPoint])
def get_user_activity(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_sync_db),
):
    """获取最近 N 天的每日用户活跃度（活跃/新增/日记/咨询）"""
    cutoff_date = datetime.utcnow().date() - timedelta(days=days - 1)

    # 一、按天聚合各指标
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

    diary_map = {r.date: r.diary_users for r in mood_day}
    cons_map = {r.date: r.cons_users for r in cons_day}
    new_map = {r.date: r.new_users for r in new_day}

    # 活跃用户：每天日记用户∪咨询用户，需分别查出 uid 集合合并
    # 为简单高效，按天批量查 uid 列表
    mood_uid_day = {}
    for r in mood_day:
        ds = r.date
        uid_rows = (
            db.query(MoodLog.user_id)
            .filter(func.date(MoodLog.created_at) == ds)
            .distinct()
            .all()
        )
        mood_uid_day[ds] = {row[0] for row in uid_rows}

    cons_uid_day = {}
    for r in cons_day:
        ds = r.date
        uid_rows = (
            db.query(Consultation.user_id)
            .filter(func.date(Consultation.created_at) == ds)
            .distinct()
            .all()
        )
        cons_uid_day[ds] = {row[0] for row in uid_rows}

    result = []
    for i in range(days):
        d = cutoff_date + timedelta(days=i)
        ds = d.isoformat()
        mood_set = mood_uid_day.get(ds, set())
        cons_set = cons_uid_day.get(ds, set())
        result.append(
            ActivityPoint(
                date=ds,
                active_users=len(mood_set | cons_set),
                new_users=new_map.get(ds, 0),
                diary_users=diary_map.get(ds, 0),
                consultation_users=cons_map.get(ds, 0),
            )
        )
    return result
