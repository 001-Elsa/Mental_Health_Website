from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database.database import get_sync_db
from database.models import MoodLog, Bookmark, Consultation, RiskEvent, User
from backend.schemas import MoodLogCreate, MoodLogOut
from backend.auth import get_current_user
from backend.services.cache import cache_service
from backend.services.risk_engine import assess_risk
from backend.services.risk_cases import OPEN_STATUSES, create_or_escalate_case

router = APIRouter(prefix="/api/mood", tags=["情绪日志"])


@router.get("/", response_model=list[MoodLogOut])
def list_mood_logs(
    user_id: str = Query(default=""),
    score: str = Query(default=""),
    db: Session = Depends(get_sync_db),
):
    """搜索公开情绪日志：可按用户ID和/或评分筛选"""
    q = db.query(MoodLog).filter(MoodLog.visibility == "公开")
    if user_id and user_id.isdigit():
        q = q.filter(MoodLog.user_id == int(user_id))
    if score:
        try:
            s = float(score)
            q = q.filter(MoodLog.score == s)
        except ValueError:
            pass
    return q.order_by(MoodLog.created_at.desc()).all()


@router.get("/mine", response_model=list[MoodLogOut])
def list_my_mood_logs(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(MoodLog).filter(
        MoodLog.user_id == current_user.id
    ).order_by(MoodLog.created_at.asc()).limit(90).all()


@router.get("/risk-status")
def get_my_risk_status(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(RiskEvent).filter(
        RiskEvent.user_id == current_user.id,
        RiskEvent.status == "pending",
    ).order_by(RiskEvent.score.desc(), RiskEvent.created_at.desc()).first()
    if not event:
        return {"level": "low", "score": 0, "reason": "", "support_actions": []}
    return {
        "level": event.level,
        "score": event.score,
        "reason": event.signals,
        "support_actions": ["联系可信任的人", "预约学校心理中心", "紧急情况下拨打 120 / 110"],
    }


@router.get("/{mid}", response_model=MoodLogOut)
def get_mood_log(mid: int, db: Session = Depends(get_sync_db)):
    obj = db.query(MoodLog).filter(
        MoodLog.id == mid,
        MoodLog.visibility == "公开",
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="日记不存在")
    return obj


@router.post("/")
def create_mood_log(
    payload: MoodLogCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    data["user_id"] = current_user.id
    mood = MoodLog(**data)
    db.add(mood)
    db.flush()
    previous = db.query(MoodLog.score).filter(
        MoodLog.user_id == current_user.id,
        MoodLog.id != mood.id,
    ).order_by(MoodLog.created_at.desc(), MoodLog.id.desc()).limit(4).all()
    scores = [float(row[0]) for row in reversed(previous)] + [float(mood.score)]
    assessment = assess_risk("", scores)
    if assessment.level != "low":
        existing_event = db.query(RiskEvent).filter(
            RiskEvent.user_id == current_user.id,
            RiskEvent.event_type == "mood_trend",
            RiskEvent.status.in_(OPEN_STATUSES),
        ).first()
        trend_consultation = None
        if existing_event and existing_event.consultation_id:
            trend_consultation = db.query(Consultation).filter(
                Consultation.id == existing_event.consultation_id
            ).first()
        if not trend_consultation:
            trend_consultation = Consultation(
                user_id=current_user.id,
                conversation_id="",
                title="情绪趋势预警",
                summary=assessment.reason,
                emotion_tag="持续低落",
                visibility="私人",
                risk_level=assessment.level,
                risk_score=assessment.score,
                risk_reason=assessment.reason,
                intervention_status="pending",
            )
            db.add(trend_consultation)
            db.flush()
        create_or_escalate_case(
            db,
            user_id=current_user.id,
            consultation=trend_consultation,
            assessment=assessment,
            excerpt=f"最近情绪评分：{' → '.join(str(score) for score in scores[-5:])}",
            event_type="mood_trend",
        )
    db.commit()
    db.refresh(mood)
    cache_service.delete("analytics:overview")
    cache_service.delete(f"analytics:mood-forecast:{current_user.id}:7")
    result = MoodLogOut.model_validate(mood).model_dump(mode="json")
    result["risk"] = {
        "level": assessment.level,
        "score": assessment.score,
        "signals": list(assessment.signals),
    }
    return result


@router.post("/{mid}/bookmark")
def toggle_bookmark(
    mid: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """切换收藏状态：已收藏则取消，未收藏则添加"""
    mood = db.query(MoodLog).filter(MoodLog.id == mid).first()
    if not mood:
        raise HTTPException(status_code=404, detail="日记不存在")

    existing = db.query(Bookmark).filter(
        Bookmark.user_id == current_user.id, Bookmark.mood_log_id == mid
    ).first()

    if existing:
        db.delete(existing)
        mood.bookmark_count = max(0, mood.bookmark_count - 1)
        db.commit()
        return {"bookmarked": False, "bookmark_count": mood.bookmark_count}
    else:
        bm = Bookmark(user_id=current_user.id, mood_log_id=mid)
        db.add(bm)
        mood.bookmark_count += 1
        db.commit()
        return {"bookmarked": True, "bookmark_count": mood.bookmark_count}
