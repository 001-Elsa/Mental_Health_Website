from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import require_admin
from backend.core.time import utc_now
from backend.services.audit import record_audit
from backend.services.article_service import invalidate_articles
from backend.services.risk_cases import (
    OPEN_STATUSES,
    InvalidRiskTransition,
    RiskOwnershipConflict,
    RiskVersionConflict,
    claim_case,
    transition_case,
)
from database.database import get_sync_db
from database.models import (
    Article,
    AdminAuditLog,
    Consultation,
    Discussion,
    MoodLog,
    Report,
    RiskEvent,
    RiskAction,
    SensitiveWord,
    User,
)

router = APIRouter(prefix="/api/admin", tags=["运营管理"])


class HandleRiskReq(BaseModel):
    status: str = Field(pattern=r"^(claimed|processing|waiting|transferred|resolved|closed|assigned|contacted|follow_up|false_positive)$")
    note: str = Field(default="", max_length=512)
    expected_version: int = Field(ge=0)
    assignee_id: int | None = None
    next_follow_up_at: datetime | None = None


class HandleReportReq(BaseModel):
    action: str = Field(pattern=r"^(dismiss|hide|restore)$")


class SensitiveWordReq(BaseModel):
    word: str = Field(min_length=1, max_length=64)
    category: str = Field(default="unsafe", max_length=32)


class RoleUpdateReq(BaseModel):
    role: str = Field(pattern=r"^(student|admin)$")


class ArticleStatusReq(BaseModel):
    status: str = Field(pattern=r"^(已发布|草稿)$")


@router.get("/overview")
def overview(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    seven_days_ago = utc_now() - timedelta(days=7)
    one_day_ago = utc_now() - timedelta(days=1)
    active_mood_users = {
        row[0]
        for row in db.query(MoodLog.user_id).filter(MoodLog.created_at >= seven_days_ago).distinct().all()
    }
    active_consult_users = {
        row[0]
        for row in db.query(Consultation.user_id).filter(Consultation.created_at >= seven_days_ago).distinct().all()
    }
    daily_users = {
        row[0] for row in db.query(MoodLog.user_id).filter(MoodLog.created_at >= one_day_ago).distinct().all()
    } | {
        row[0] for row in db.query(Consultation.user_id).filter(Consultation.created_at >= one_day_ago).distinct().all()
    }
    return {
        "total_users": db.query(func.count(User.id)).scalar() or 0,
        "active_users_1d": len(daily_users),
        "active_users_7d": len(active_mood_users | active_consult_users),
        "consultations_7d": db.query(func.count(Consultation.id)).filter(Consultation.created_at >= seven_days_ago).scalar() or 0,
        "pending_risks": db.query(func.count(RiskEvent.id)).filter(RiskEvent.status.in_(OPEN_STATUSES)).scalar() or 0,
        "critical_risks": db.query(func.count(RiskEvent.id)).filter(
            RiskEvent.status.in_(OPEN_STATUSES), RiskEvent.level == "critical"
        ).scalar() or 0,
        "overdue_risks": db.query(func.count(RiskEvent.id)).filter(
            RiskEvent.status.in_(OPEN_STATUSES),
            RiskEvent.due_at.isnot(None),
            RiskEvent.due_at < utc_now(),
        ).scalar() or 0,
        "pending_reports": db.query(func.count(Report.id)).filter(Report.status == "pending").scalar() or 0,
        "pending_content": db.query(func.count(Discussion.id)).filter(Discussion.status == "pending_review").scalar() or 0,
        "avg_mood_7d": round(db.query(func.avg(MoodLog.score)).filter(MoodLog.created_at >= seven_days_ago).scalar() or 0, 1),
        "community_posts_7d": db.query(func.count(Discussion.id)).filter(Discussion.created_at >= seven_days_ago).scalar() or 0,
    }


@router.get("/trends")
def operation_trends(
    days: int = Query(default=14, ge=7, le=90),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    cutoff = utc_now().date() - timedelta(days=days - 1)
    mood_rows = db.query(
        func.date(MoodLog.created_at).label("date"),
        func.round(func.avg(MoodLog.score), 1).label("avg_mood"),
    ).filter(func.date(MoodLog.created_at) >= cutoff.isoformat()).group_by(func.date(MoodLog.created_at)).all()
    consult_rows = db.query(
        func.date(Consultation.created_at).label("date"),
        func.count(Consultation.id).label("count"),
    ).filter(func.date(Consultation.created_at) >= cutoff.isoformat()).group_by(func.date(Consultation.created_at)).all()
    risk_rows = db.query(
        func.date(RiskEvent.created_at).label("date"),
        func.count(RiskEvent.id).label("count"),
    ).filter(func.date(RiskEvent.created_at) >= cutoff.isoformat()).group_by(func.date(RiskEvent.created_at)).all()
    mood_map = {row.date: float(row.avg_mood) for row in mood_rows}
    consult_map = {row.date: row.count for row in consult_rows}
    risk_map = {row.date: row.count for row in risk_rows}
    return [
        {
            "date": (cutoff + timedelta(days=index)).isoformat(),
            "avg_mood": mood_map.get((cutoff + timedelta(days=index)).isoformat()),
            "consultations": consult_map.get((cutoff + timedelta(days=index)).isoformat(), 0),
            "risk_events": risk_map.get((cutoff + timedelta(days=index)).isoformat(), 0),
        }
        for index in range(days)
    ]


@router.get("/risk-events")
def risk_events(
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(RiskEvent)
    if status == "open":
        query = query.filter(RiskEvent.status.in_(OPEN_STATUSES))
    elif status:
        query = query.filter(RiskEvent.status == status)
    rows = query.order_by(RiskEvent.score.desc(), RiskEvent.created_at.desc()).limit(limit).all()
    user_ids = {row.user_id for row in rows} | {row.assigned_to for row in rows if row.assigned_to}
    users = {row.id: row for row in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "nickname": users.get(row.user_id).nickname if users.get(row.user_id) else f"用户 {row.user_id}",
            "consultation_id": row.consultation_id,
            "conversation_id": row.conversation_id,
            "level": row.level,
            "score": row.score,
            "signals": row.signals,
            "excerpt": row.excerpt,
            "status": row.status,
            "assigned_to": row.assigned_to,
            "assignee_name": users.get(row.assigned_to).nickname if users.get(row.assigned_to) else "",
            "due_at": row.due_at,
            "overdue": bool(row.due_at and row.due_at < utc_now() and row.status in OPEN_STATUSES),
            "next_follow_up_at": row.next_follow_up_at,
            "version": row.version,
            "event_type": row.event_type,
            "model_level": row.model_level,
            "model_reason": row.model_reason,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.patch("/risk-events/{event_id}")
def handle_risk_event(
    event_id: int,
    payload: HandleRiskReq,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    event = db.query(RiskEvent).filter(RiskEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="风险事件不存在")
    if payload.status in {"resolved", "false_positive"} and len(payload.note.strip()) < 2:
        raise HTTPException(status_code=422, detail="结案必须填写处置说明")
    if payload.assignee_id:
        assignee = db.query(User).filter(User.id == payload.assignee_id, User.role == "admin").first()
        if not assignee:
            raise HTTPException(status_code=422, detail="负责人必须是有效管理员")
    previous_status = event.status
    try:
        updated = transition_case(
            db,
            event=event,
            actor_id=current_user.id,
            to_status=payload.status,
            expected_version=payload.expected_version,
            note=payload.note.strip(),
            assignee_id=payload.assignee_id,
            next_follow_up_at=payload.next_follow_up_at,
            request_id=getattr(request.state, "request_id", ""),
            ip_address=request.client.host if request.client else "",
        )
    except RiskVersionConflict as exc:
        raise HTTPException(status_code=409, detail="案例已被其他管理员更新，请刷新后重试") from exc
    except InvalidRiskTransition as exc:
        raise HTTPException(status_code=422, detail=f"不允许的案例状态流转：{exc}") from exc
    except RiskOwnershipConflict as exc:
        raise HTTPException(status_code=403, detail="该案例已由其他管理员负责，请先转交") from exc
    consult = db.query(Consultation).filter(Consultation.id == updated.consultation_id).first()
    if consult:
        consult.intervention_status = payload.status
    record_audit(
        db,
        actor_id=current_user.id,
        action=f"risk.{payload.status}",
        target_type="risk_event",
        target_id=event_id,
        detail={"from": previous_status, "to": payload.status, "note": payload.note},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True, "status": updated.status, "version": updated.version}


@router.post("/risk-events/{event_id}/claim")
def claim_risk_event(
    event_id: int,
    request: Request,
    expected_version: int = Query(ge=0),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    try:
        event = claim_case(
            db,
            event_id=event_id,
            actor_id=current_user.id,
            expected_version=expected_version,
            request_id=getattr(request.state, "request_id", ""),
            ip_address=request.client.host if request.client else "",
        )
    except RiskVersionConflict as exc:
        raise HTTPException(status_code=409, detail="案例已被其他管理员领取或版本已更新") from exc
    record_audit(
        db,
        actor_id=current_user.id,
        action="risk.claimed",
        target_type="risk_event",
        target_id=event_id,
        detail={"to": "claimed"},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True, "status": event.status, "version": event.version, "assigned_to": event.assigned_to}


@router.get("/risk-events/{event_id}/timeline")
def risk_event_timeline(
    event_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    if not db.query(RiskEvent.id).filter(RiskEvent.id == event_id).first():
        raise HTTPException(status_code=404, detail="风险事件不存在")
    rows = db.query(RiskAction).filter(
        RiskAction.risk_event_id == event_id
    ).order_by(RiskAction.created_at.asc(), RiskAction.id.asc()).all()
    actor_ids = {row.actor_id for row in rows if row.actor_id}
    actors = {row.id: row.nickname for row in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}
    return [
        {
            "id": row.id,
            "action": row.action,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "note": row.note,
            "request_id": row.request_id,
            "ip_address": row.ip_address,
            "actor_id": row.actor_id,
            "actor_name": actors.get(row.actor_id, "系统"),
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/audit-logs")
def audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    rows = db.query(AdminAuditLog).order_by(
        AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()
    ).limit(limit).all()
    actor_ids = {row.actor_id for row in rows}
    actors = {row.id: row.nickname for row in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "actor_name": actors.get(row.actor_id, f"管理员 {row.actor_id}"),
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "detail": row.detail,
            "request_id": row.request_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/reports")
def reports(
    status: str = Query(default="pending"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(Report)
    if status:
        query = query.filter(Report.status == status)
    return query.order_by(Report.created_at.desc()).limit(100).all()


@router.patch("/reports/{report_id}")
def handle_report(
    report_id: int,
    payload: HandleReportReq,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="举报不存在")
    if report.target_type == "discussion":
        discussion = db.query(Discussion).filter(Discussion.id == report.target_id).first()
        if discussion:
            if payload.action == "hide":
                discussion.status = "hidden"
                discussion.moderation_reason = f"举报审核：{report.reason}"
            elif payload.action == "restore":
                discussion.status = "published"
                discussion.moderation_reason = ""
    report.status = "resolved" if payload.action != "dismiss" else "dismissed"
    report.handled_by = current_user.id
    report.handled_at = utc_now()
    record_audit(
        db,
        actor_id=current_user.id,
        action=f"report.{payload.action}",
        target_type="report",
        target_id=report_id,
        detail={"reason": report.reason, "target_id": report.target_id},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True, "status": report.status}


@router.get("/moderation")
def moderation_queue(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    return db.query(Discussion).filter(Discussion.status == "pending_review").order_by(Discussion.created_at.asc()).all()


@router.patch("/moderation/{discussion_id}")
def moderate_discussion(
    discussion_id: int,
    request: Request,
    action: str = Query(pattern=r"^(approve|hide)$"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    if not discussion:
        raise HTTPException(status_code=404, detail="讨论不存在")
    discussion.status = "published" if action == "approve" else "hidden"
    record_audit(
        db,
        actor_id=current_user.id,
        action=f"moderation.{action}",
        target_type="discussion",
        target_id=discussion_id,
        detail={"reason": discussion.moderation_reason},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True, "status": discussion.status}


@router.get("/sensitive-words")
def list_sensitive_words(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    return db.query(SensitiveWord).order_by(SensitiveWord.created_at.desc()).all()


@router.post("/sensitive-words")
def create_sensitive_word(
    payload: SensitiveWordReq,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    word = payload.word.strip()
    if db.query(SensitiveWord).filter(SensitiveWord.word == word).first():
        raise HTTPException(status_code=409, detail="敏感词已存在")
    item = SensitiveWord(word=word, category=payload.category)
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=current_user.id,
        action="sensitive_word.create",
        target_type="sensitive_word",
        target_id=item.id,
        detail={"word": word, "category": payload.category},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    db.refresh(item)
    return item


@router.patch("/sensitive-words/{word_id}/toggle")
def toggle_sensitive_word(
    word_id: int,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    item = db.query(SensitiveWord).filter(SensitiveWord.id == word_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="敏感词不存在")
    item.enabled = not item.enabled
    record_audit(
        db,
        actor_id=current_user.id,
        action="sensitive_word.toggle",
        target_type="sensitive_word",
        target_id=word_id,
        detail={"enabled": item.enabled},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True, "enabled": item.enabled}


@router.delete("/sensitive-words/{word_id}")
def delete_sensitive_word(
    word_id: int,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    item = db.query(SensitiveWord).filter(SensitiveWord.id == word_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="敏感词不存在")
    detail = {"word": item.word, "category": item.category}
    db.delete(item)
    record_audit(
        db,
        actor_id=current_user.id,
        action="sensitive_word.delete",
        target_type="sensitive_word",
        target_id=word_id,
        detail=detail,
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True}


@router.get("/users")
def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    rows = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "nickname": row.nickname,
            "phone": f"{row.phone[:3]}****{row.phone[-4:]}" if len(row.phone) >= 7 else "",
            "role": row.role,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: RoleUpdateReq,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="不能移除自己的管理员权限")
    previous_role = user.role
    user.role = payload.role
    record_audit(
        db,
        actor_id=current_user.id,
        action="user.role_update",
        target_type="user",
        target_id=user_id,
        detail={"from": previous_role, "to": payload.role},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    return {"ok": True, "role": user.role}


@router.get("/articles")
def list_admin_articles(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    return db.query(Article).order_by(Article.created_at.desc()).limit(200).all()


@router.patch("/articles/{article_id}/status")
def update_article_status(
    article_id: int,
    payload: ArticleStatusReq,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    previous_status = article.status
    article.status = payload.status
    record_audit(
        db,
        actor_id=current_user.id,
        action="article.status_update",
        target_type="article",
        target_id=article_id,
        detail={"from": previous_status, "to": payload.status},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    invalidate_articles()
    return {"ok": True, "status": article.status}
