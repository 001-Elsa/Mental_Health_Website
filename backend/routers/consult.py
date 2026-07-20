from datetime import datetime

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sa_func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, aliased

from backend.auth import get_current_user, get_current_user_async
from backend.services.ai_client import ai_client
from backend.services.cache import cache_service
from backend.services.conversation_memory import compress_history
from backend.services.idempotency import IdempotencyInProgress, begin_operation, complete_operation
from backend.services.risk_engine import RiskAssessment, assess_risk, infer_emotion
from backend.services.risk_cases import create_or_escalate_case
from backend.services.user_profile import recommend_exercises, update_user_profile
from database.database import AsyncSessionLocal, get_async_db, get_sync_db
from database.models import ChatMessage, Consultation, MoodLog, User, UserProfile

router = APIRouter(prefix="/api/consult", tags=["AI咨询"])


class ChatReq(BaseModel):
    conversation_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    request_key: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")
    message: str = Field(min_length=1, max_length=2000)
    visibility: str = Field(default="私人", pattern=r"^(公开|私人)$")


class ConversationUpdateReq(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    pinned: bool | None = None


def _support_actions(level: str) -> list[str]:
    if level in {"critical", "high"}:
        return ["离开危险环境", "联系可信任的人陪伴", "拨打 120 / 110 或当地心理援助热线"]
    if level == "medium":
        return ["暂停独处并联系朋友", "记录触发因素", "预约学校心理中心"]
    return []


@router.post("/chat")
async def chat(
    payload: ChatReq,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Persist a multi-turn AI conversation and its explainable risk assessment."""
    idempotency_record = None
    if payload.request_key:
        try:
            idempotency_record, cached_response = begin_operation(
                db,
                user_id=current_user.id,
                operation="consult.chat",
                key=payload.request_key,
            )
        except IdempotencyInProgress as exc:
            raise HTTPException(status_code=409, detail="相同请求正在处理中，请稍后重试") from exc
        if cached_response is not None:
            return cached_response
    if cache_service.increment(f"rate:consult:{current_user.id}", 60) > 20:
        if idempotency_record:
            db.delete(idempotency_record)
            db.commit()
        raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试")
    message = payload.message.strip()
    existing_consult = (
        db.query(Consultation)
        .filter(Consultation.conversation_id == payload.conversation_id)
        .first()
    )
    if existing_consult and existing_consult.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="该会话不属于当前用户")

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == payload.conversation_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    mood_rows = (
        db.query(MoodLog.score)
        .filter(MoodLog.user_id == current_user.id)
        .order_by(MoodLog.created_at.desc())
        .limit(5)
        .all()
    )
    mood_scores = list(reversed([float(row[0]) for row in mood_rows]))
    assessment = assess_risk(message, mood_scores)
    model_review = await ai_client.review_risk(message) if assessment.level == "medium" else None
    risk_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if model_review and risk_rank[model_review[0]] > risk_rank[assessment.level]:
        model_level, model_reason = model_review
        assessment = RiskAssessment(
            level=model_level,
            score=max(assessment.score, 80 if model_level == "critical" else 55),
            signals=(*assessment.signals, f"模型复核：{model_reason}"),
        )

    consult = existing_consult or Consultation(
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        title=message[:50],
        visibility=payload.visibility,
    )
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if profile and profile.summary:
        history = [{"role": "system", "content": f"用户支持画像：{profile.summary}"}, *history]
    if consult.memory_summary:
        history = [{"role": "system", "content": f"此前对话摘要：{consult.memory_summary}"}, *history[-10:]]
    reply = await ai_client.chat(history, message, assessment)

    if not existing_consult:
        db.add(consult)
        db.flush()

    now = datetime.utcnow()
    consult.emotion_tag = infer_emotion(message)
    consult.last_message_at = now
    consult.risk_score = max(consult.risk_score or 0, assessment.score)
    if risk_rank[assessment.level] >= risk_rank.get(consult.risk_level, 0):
        consult.risk_level = assessment.level
        consult.risk_reason = assessment.reason
    if assessment.requires_intervention:
        consult.intervention_status = "pending"
        create_or_escalate_case(
            db,
            user_id=current_user.id,
            consultation=consult,
            assessment=assessment,
            excerpt=message,
            model_review=model_review,
        )

    db.add(ChatMessage(conversation_id=payload.conversation_id, role="user", content=message))
    db.add(ChatMessage(conversation_id=payload.conversation_id, role="assistant", content=reply))
    complete_history = [
        *[{"role": row.role, "content": row.content} for row in history_rows],
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ]
    consult.summary = compress_history(complete_history, max_chars=260)
    consult.message_count = len(history_rows) + 2
    if len(complete_history) >= 12:
        consult.memory_summary = compress_history(complete_history[:-6])
    user_messages = [item["content"] for item in complete_history if item["role"] == "user"]
    profile = update_user_profile(db, current_user.id, user_messages)
    exercises = recommend_exercises(db, consult.emotion_tag)
    if idempotency_record:
        db.flush()
    else:
        db.commit()
    cache_service.delete("analytics:overview")

    response = {
        "reply": reply,
        "message_count": len(history_rows) + 2,
        "emotion": consult.emotion_tag,
        "risk": {
            "level": assessment.level,
            "score": assessment.score,
            "signals": list(assessment.signals),
            "requires_intervention": assessment.requires_intervention,
        },
        "support_actions": _support_actions(assessment.level),
        "profile_summary": profile.summary,
        "recommended_exercises": [
            {
                "id": exercise.id,
                "title": exercise.title,
                "category": exercise.category,
                "description": exercise.description,
                "duration_minutes": exercise.duration_minutes,
                "steps": exercise.steps,
            }
            for exercise in exercises
        ],
    }
    if idempotency_record:
        complete_operation(db, idempotency_record, response)
    return response


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _persist_streamed_chat_sync(
    db: Session,
    *,
    user_id: int,
    payload: dict,
    message: str,
    reply: str,
    assessment: RiskAssessment,
    model_review: tuple[str, str] | None,
) -> None:
    """Synchronous ORM unit invoked through AsyncSession.run_sync."""
    consult = db.query(Consultation).filter(
            Consultation.conversation_id == payload["conversation_id"],
            Consultation.user_id == user_id,
        ).first()
    if not consult:
        consult = Consultation(
                user_id=user_id,
                conversation_id=payload["conversation_id"],
                title=message[:50],
                visibility=payload["visibility"],
            )
        db.add(consult)
        db.flush()
    history_rows = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == payload["conversation_id"]
        ).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).all()
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    consult.emotion_tag = infer_emotion(message)
    consult.last_message_at = datetime.utcnow()
    consult.risk_score = max(consult.risk_score or 0, assessment.score)
    if rank[assessment.level] >= rank.get(consult.risk_level, 0):
        consult.risk_level = assessment.level
        consult.risk_reason = assessment.reason
    if assessment.requires_intervention:
        consult.intervention_status = "pending"
        create_or_escalate_case(
            db, user_id=user_id, consultation=consult, assessment=assessment,
            excerpt=message, model_review=model_review,
        )
    db.add(ChatMessage(conversation_id=payload["conversation_id"], role="user", content=message))
    db.add(ChatMessage(conversation_id=payload["conversation_id"], role="assistant", content=reply))
    complete_history = [
        *[{"role": row.role, "content": row.content} for row in history_rows],
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ]
    consult.summary = compress_history(complete_history, max_chars=260)
    consult.message_count = len(history_rows) + 2
    if len(complete_history) >= 12:
        consult.memory_summary = compress_history(complete_history[:-6])
    user_messages = [item["content"] for item in complete_history if item["role"] == "user"]
    update_user_profile(db, user_id, user_messages)


async def _persist_streamed_chat(**kwargs) -> None:
    async with AsyncSessionLocal() as db:
        await db.run_sync(lambda sync_db: _persist_streamed_chat_sync(sync_db, **kwargs))
        await db.commit()
    cache_service.delete(f"analytics:overview:user:{kwargs['user_id']}")


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatReq,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """Stream tokens as SSE and persist the completed answer in a background task."""
    if cache_service.increment(f"rate_limit:ai:{current_user.id}", 60) > 20:
        raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试")
    message = payload.message.strip()
    existing = (await db.execute(select(Consultation).where(
        Consultation.conversation_id == payload.conversation_id
    ))).scalar_one_or_none()
    if existing and existing.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="该会话不属于当前用户")
    history_rows = (await db.execute(select(ChatMessage).where(
        ChatMessage.conversation_id == payload.conversation_id
    ).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()))).scalars().all()
    mood_rows = (await db.execute(select(MoodLog.score).where(
        MoodLog.user_id == current_user.id
    ).order_by(MoodLog.created_at.desc()).limit(5))).all()
    assessment = assess_risk(message, list(reversed([float(row[0]) for row in mood_rows])))
    model_review = await ai_client.review_risk(message) if assessment.level == "medium" else None
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    profile = (await db.execute(select(UserProfile).where(
        UserProfile.user_id == current_user.id
    ))).scalar_one_or_none()
    if profile and profile.summary:
        history = [{"role": "system", "content": f"用户支持画像：{profile.summary}"}, *history]
    if existing and existing.memory_summary:
        history = [{"role": "system", "content": f"此前对话摘要：{existing.memory_summary}"}, *history[-10:]]
    user_id = current_user.id
    payload_data = payload.model_dump()

    async def events():
        chunks: list[str] = []
        yield _sse("meta", {
            "request_id": getattr(request.state, "request_id", ""),
            "risk": {"level": assessment.level, "score": assessment.score},
        })
        try:
            async for chunk in ai_client.stream_chat(history, message, assessment):
                if await request.is_disconnected():
                    return
                chunks.append(chunk)
                yield _sse("token", {"content": chunk})
        except Exception:
            yield _sse("error", {"detail": "AI 流式响应中断，请稍后重试"})
            return
        reply = "".join(chunks)
        background_tasks.add_task(
            _persist_streamed_chat,
            user_id=user_id,
            payload=payload_data,
            message=message,
            reply=reply,
            assessment=assessment,
            model_review=model_review,
        )
        yield _sse("done", {"message_count": len(history_rows) + 2})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background_tasks,
    )


@router.get("/conversations")
def list_conversations(
    q: str = Query(default="", max_length=100),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(
            ChatMessage.conversation_id,
            sa_func.min(ChatMessage.created_at).label("started"),
            sa_func.count(ChatMessage.id).label("msg_count"),
            Consultation.pinned.label("pinned"),
        )
        .join(Consultation, Consultation.conversation_id == ChatMessage.conversation_id)
        .filter(Consultation.user_id == current_user.id)
    )
    search_term = q.strip()
    if search_term:
        search_message = aliased(ChatMessage)
        matching_message = db.query(search_message.id).filter(
            search_message.conversation_id == Consultation.conversation_id,
            search_message.content.contains(search_term, autoescape=True),
        ).exists()
        query = query.filter(or_(
            Consultation.title.contains(search_term, autoescape=True),
            Consultation.summary.contains(search_term, autoescape=True),
            matching_message,
        ))
    rows = (
        query.group_by(ChatMessage.conversation_id, Consultation.pinned)
        .order_by(Consultation.pinned.desc(), sa_func.max(ChatMessage.created_at).desc())
        .all()
    )
    result = []
    for row in rows:
        consult = db.query(Consultation).filter(Consultation.conversation_id == row.conversation_id).first()
        result.append(
            {
                "consultation_id": consult.id,
                "conversation_id": row.conversation_id,
                "title": consult.title or "新对话",
                "message_count": row.msg_count,
                "visibility": consult.visibility,
                "pinned": bool(row.pinned),
                "emotion_tag": consult.emotion_tag,
                "risk_level": consult.risk_level,
                "started_at": row.started.isoformat() if row.started else "",
            }
        )
    return result


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateReq,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    consult = db.query(Consultation).filter(
        Consultation.conversation_id == conversation_id,
        Consultation.user_id == current_user.id,
    ).first()
    if not consult:
        raise HTTPException(status_code=404, detail="会话不存在")
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="会话标题不能为空")
        consult.title = title
    if payload.pinned is not None:
        consult.pinned = payload.pinned
    db.commit()
    return {
        "conversation_id": consult.conversation_id,
        "title": consult.title,
        "pinned": consult.pinned,
    }


@router.patch("/conversations/{conversation_id}/visibility")
def toggle_visibility(
    conversation_id: str,
    visibility: str = "私人",
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    if visibility not in {"公开", "私人"}:
        raise HTTPException(status_code=422, detail="无效的可见范围")
    consult = db.query(Consultation).filter(Consultation.conversation_id == conversation_id).first()
    if not consult or consult.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    consult.visibility = visibility
    db.commit()
    return {"conversation_id": conversation_id, "visibility": visibility}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    consult = db.query(Consultation).filter(Consultation.conversation_id == conversation_id).first()
    if not consult or consult.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).delete()
    db.delete(consult)
    db.commit()
    return {"ok": True}


@router.get("/history/{conversation_id}")
def get_history(
    conversation_id: str,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    consult = db.query(Consultation).filter(Consultation.conversation_id == conversation_id).first()
    if consult and consult.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看该会话")
    if not consult:
        return []
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    return [
        {"role": row.role, "content": row.content, "created_at": row.created_at.isoformat()}
        for row in rows
    ]
