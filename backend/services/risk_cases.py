from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.services.risk_engine import RiskAssessment
from backend.services.observability import RISK_CASES, RISK_OPEN, RISK_SLA_OVERDUE
from backend.core.time import utc_now
from database.models import Consultation, RiskAction, RiskEvent, User, UserNotification

OPEN_STATUSES = {
    "pending", "claimed", "processing", "waiting", "transferred",
    # Backwards-compatible workflow names used by existing clients.
    "assigned", "contacted", "follow_up",
}
TRANSITIONS = {
    "pending": {"claimed", "assigned", "contacted", "resolved", "false_positive"},
    "claimed": {"processing", "transferred"},
    "processing": {"waiting", "transferred", "resolved", "false_positive"},
    "waiting": {"processing", "resolved"},
    "transferred": {"claimed", "assigned"},
    "resolved": {"closed"},
    "assigned": {"contacted", "resolved", "false_positive"},
    "contacted": {"follow_up", "resolved", "false_positive"},
    "follow_up": {"contacted", "resolved", "false_positive"},
}
RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class InvalidRiskTransition(Exception):
    pass


class RiskVersionConflict(Exception):
    pass


class RiskOwnershipConflict(Exception):
    pass


def due_at_for_level(level: str, now: datetime | None = None) -> datetime:
    current = now or utc_now()
    if level in {"critical", "high"}:
        return current + timedelta(minutes=5)
    if level == "medium":
        return current + timedelta(minutes=30)
    return current + timedelta(hours=24)


def _fallback_sla_operator(db: Session) -> int | None:
    """Return an operations user for unassigned SLA reminders, if available."""
    row = db.query(User.id).filter(User.role == "admin").order_by(User.id.asc()).first()
    return int(row[0]) if row else None


def create_or_escalate_case(
    db: Session,
    *,
    user_id: int,
    consultation: Consultation,
    assessment: RiskAssessment,
    excerpt: str,
    event_type: str = "conversation",
    model_review: tuple[str, str] | None = None,
) -> RiskEvent:
    # PostgreSQL serializes case creation per user while allowing unrelated
    # users to proceed concurrently.  This closes the read-then-insert race.
    if db.bind and db.bind.dialect.name == "postgresql":
        db.query(User.id).filter(User.id == user_id).with_for_update().one()
    merge_cutoff = utc_now() - timedelta(minutes=30)
    event = db.query(RiskEvent).filter(
        RiskEvent.user_id == user_id,
        RiskEvent.event_type == event_type,
        RiskEvent.status.in_(OPEN_STATUSES),
        RiskEvent.created_at >= merge_cutoff,
    ).order_by(RiskEvent.created_at.desc()).first()
    if event:
        previous_level = event.level
        event.score = max(event.score, assessment.score)
        if RISK_RANK[assessment.level] > RISK_RANK.get(event.level, 0):
            event.level = assessment.level
            event.due_at = min(filter(None, [event.due_at, due_at_for_level(assessment.level)]))
        event.signals = assessment.reason
        event.excerpt = excerpt[:300]
        if model_review:
            event.model_level, event.model_reason = model_review
        event.version += 1
        db.add(RiskAction(
            risk_event_id=event.id,
            action="escalated" if previous_level != event.level else "signal_updated",
            from_status=event.status,
            to_status=event.status,
            note=assessment.reason[:512],
        ))
        RISK_CASES.labels("merged", event.level).inc()
        return event

    event = RiskEvent(
        user_id=user_id,
        consultation_id=consultation.id,
        conversation_id=consultation.conversation_id,
        event_type=event_type,
        level=assessment.level,
        score=assessment.score,
        signals=assessment.reason,
        excerpt=excerpt[:300],
        model_level=model_review[0] if model_review else "",
        model_reason=model_review[1] if model_review else "",
        due_at=due_at_for_level(assessment.level),
    )
    db.add(event)
    db.flush()
    db.add(RiskAction(
        risk_event_id=event.id,
        action="created",
        from_status="",
        to_status="pending",
        note=assessment.reason[:512],
    ))
    RISK_CASES.labels("created", event.level).inc()
    return event


def claim_case(
    db: Session,
    *,
    event_id: int,
    actor_id: int,
    expected_version: int,
    request_id: str = "",
    ip_address: str = "",
) -> RiskEvent:
    """Atomically claim one pending/transferred case; exactly one concurrent caller wins."""
    changed = db.query(RiskEvent).filter(
        RiskEvent.id == event_id,
        RiskEvent.status.in_({"pending", "transferred"}),
        RiskEvent.version == expected_version,
    ).update(
        {
            "assigned_to": actor_id,
            "status": "claimed",
            "version": expected_version + 1,
        },
        synchronize_session=False,
    )
    if changed != 1:
        db.rollback()
        raise RiskVersionConflict
    db.add(RiskAction(
        risk_event_id=event_id,
        actor_id=actor_id,
        action="claimed",
        from_status="pending",
        to_status="claimed",
        note="管理员领取案例",
        request_id=request_id,
        ip_address=ip_address,
    ))
    db.flush()
    db.expire_all()
    event = db.query(RiskEvent).filter(RiskEvent.id == event_id).first()
    RISK_CASES.labels("claimed", event.level).inc()
    return event


def transition_case(
    db: Session,
    *,
    event: RiskEvent,
    actor_id: int,
    to_status: str,
    expected_version: int,
    note: str = "",
    assignee_id: int | None = None,
    next_follow_up_at: datetime | None = None,
    request_id: str = "",
    ip_address: str = "",
) -> RiskEvent:
    if event.version != expected_version:
        raise RiskVersionConflict
    if to_status not in TRANSITIONS.get(event.status, set()):
        raise InvalidRiskTransition(f"{event.status} -> {to_status}")
    if event.assigned_to and event.assigned_to != actor_id and to_status != "transferred":
        raise RiskOwnershipConflict
    if to_status == "follow_up" and (not next_follow_up_at or next_follow_up_at <= utc_now()):
        raise InvalidRiskTransition("follow_up requires a future next_follow_up_at")

    now = utc_now()
    updates: dict = {"status": to_status, "version": expected_version + 1}
    if to_status in {"assigned", "claimed"}:
        updates["assigned_to"] = assignee_id or actor_id
    if to_status == "transferred":
        if not assignee_id or assignee_id == actor_id:
            raise InvalidRiskTransition("transferred requires another assignee")
        updates["assigned_to"] = assignee_id
    elif event.assigned_to is None:
        updates["assigned_to"] = actor_id
    if to_status == "follow_up":
        updates["next_follow_up_at"] = next_follow_up_at
    if to_status in {"resolved", "closed", "false_positive"}:
        updates.update({
            "handled_by": actor_id,
            "handled_note": note,
            "handled_at": now,
            "next_follow_up_at": None,
        })

    changed = db.query(RiskEvent).filter(
        RiskEvent.id == event.id,
        RiskEvent.version == expected_version,
    ).update(updates, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise RiskVersionConflict
    db.add(RiskAction(
        risk_event_id=event.id,
        actor_id=actor_id,
        action=to_status,
        from_status=event.status,
        to_status=to_status,
        note=note,
        request_id=request_id,
        ip_address=ip_address,
    ))
    if to_status in {"contacted", "follow_up", "waiting", "resolved"}:
        messages = {
            "contacted": ("支持进展已更新", "平台支持人员已开始跟进。紧急情况下请优先联系现实中的可信任人员或拨打 120 / 110。"),
            "follow_up": ("后续支持已安排", "平台已记录后续关注时间，你仍可以继续记录状态或联系学校心理中心。"),
            "resolved": ("本次支持记录已完成", "本次支持记录已完成。如再次需要支持，可以继续使用 AI 倾听或预约学校心理中心。"),
            "waiting": ("等待你的反馈", "支持人员已记录当前进展，你可以在方便时继续反馈；紧急情况请联系现实支持。"),
        }
        title, content = messages[to_status]
        db.add(UserNotification(
            user_id=event.user_id,
            notification_type="risk_support",
            title=title,
            content=content,
            link="/dashboard",
        ))
    db.flush()
    db.expire_all()
    updated = db.query(RiskEvent).filter(RiskEvent.id == event.id).first()
    RISK_CASES.labels("transitioned", updated.level).inc()
    return updated


def scan_and_escalate_overdue(db: Session, now: datetime | None = None) -> int:
    """Append one SLA escalation record and notification per overdue case."""
    current = now or utc_now()
    rows = db.query(RiskEvent).filter(
        RiskEvent.status.in_(OPEN_STATUSES),
        RiskEvent.due_at.isnot(None),
        RiskEvent.due_at < current,
    ).all()
    escalated = 0
    for event in rows:
        already_recorded = db.query(RiskAction.id).filter(
            RiskAction.risk_event_id == event.id,
            RiskAction.action == "sla_escalated",
        ).first()
        if already_recorded:
            continue
        savepoint = db.begin_nested()
        db.add(RiskAction(
            risk_event_id=event.id,
            action="sla_escalated",
            from_status=event.status,
            to_status=event.status,
            note=f"案例超过 {event.level} 级别处置时限",
        ))
        try:
            db.flush()
        except IntegrityError:
            savepoint.rollback()
            continue
        else:
            savepoint.commit()
        event.score = min(100, event.score + 5)
        event.version += 1
        db.add(UserNotification(
            # A missing operator is intentionally not replaced by the student.
            # User id 0 is an unassigned operational inbox, not a user account.
            user_id=event.assigned_to or _fallback_sla_operator(db) or 0,
            notification_type="risk_sla",
            title="风险案例已超过 SLA",
            content=f"案例 #{event.id} 已超过响应时限，请立即处理。",
            link="/admin",
        ))
        RISK_CASES.labels("sla_escalated", event.level).inc()
        escalated += 1
    if escalated:
        db.commit()
    overdue_count = len(rows)
    RISK_SLA_OVERDUE.set(overdue_count)
    for level in RISK_RANK:
        RISK_OPEN.labels(level).set(
            db.query(RiskEvent.id).filter(
                RiskEvent.status.in_(OPEN_STATUSES), RiskEvent.level == level
            ).count()
        )
    return escalated
