from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_current_user, get_optional_user
from backend.schemas import DiscussionCreate, DiscussionOut, PlazaMessageCreate, PlazaMessageOut, ReplyCreate, ReplyOut
from backend.services.content_moderation import moderate_content
from database.database import get_sync_db
from database.models import Discussion, DiscussionLike, PlazaMessage, Reply, Report, User

router = APIRouter(prefix="/api/discussions", tags=["社区互助"])

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "community"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MEDIA_TYPES = {
    "image/jpeg": ("image", ".jpg", 5 * 1024 * 1024),
    "image/png": ("image", ".png", 5 * 1024 * 1024),
    "image/webp": ("image", ".webp", 5 * 1024 * 1024),
    "image/gif": ("image", ".gif", 5 * 1024 * 1024),
    "audio/webm": ("audio", ".webm", 12 * 1024 * 1024),
    "audio/ogg": ("audio", ".ogg", 12 * 1024 * 1024),
    "audio/mpeg": ("audio", ".mp3", 12 * 1024 * 1024),
    "audio/wav": ("audio", ".wav", 12 * 1024 * 1024),
    "audio/mp4": ("audio", ".m4a", 12 * 1024 * 1024),
    "audio/aac": ("audio", ".aac", 12 * 1024 * 1024),
}


class PlazaConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)

    async def broadcast(self, payload: dict):
        stale: list[WebSocket] = []
        for websocket in tuple(self.connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


plaza_connections = PlazaConnectionManager()


def _validate_media_urls(image_url: str, audio_url: str) -> None:
    for value in (image_url, audio_url):
        if value and not value.startswith("/uploads/community/"):
            raise HTTPException(status_code=422, detail="媒体地址无效，请先通过上传接口提交文件")


def _plaza_out(message: PlazaMessage, author_name: str) -> dict:
    return {
        "id": message.id,
        "user_id": message.user_id,
        "author_name": author_name or "同学",
        "content": message.content,
        "image_url": message.image_url,
        "audio_url": message.audio_url,
        "status": message.status,
        "created_at": message.created_at,
    }


class ReportCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=64)
    detail: str = Field(default="", max_length=512)


@router.get("/", response_model=list[DiscussionOut])
def list_discussions(
    title: str = Query(default=""),
    category: str = Query(default=""),
    db: Session = Depends(get_sync_db),
):
    query = db.query(Discussion).filter(
        Discussion.status == "published",
        Discussion.visibility == "公开",
    )
    if title:
        query = query.filter(Discussion.title.contains(title))
    if category:
        query = query.filter(Discussion.category == category)
    return query.order_by(Discussion.created_at.desc()).all()


@router.get("/mine", response_model=list[DiscussionOut])
def list_my_discussions(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Discussion).filter(
        Discussion.user_id == current_user.id
    ).order_by(Discussion.created_at.desc()).all()


@router.post("/media")
async def upload_community_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    media = MEDIA_TYPES.get(content_type)
    if not media:
        raise HTTPException(status_code=415, detail="仅支持常见图片或音频格式")
    media_type, suffix, max_bytes = media
    content = await file.read(max_bytes + 1)
    await file.close()
    if len(content) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"文件不能超过 {limit_mb}MB")
    if not content:
        raise HTTPException(status_code=422, detail="不能上传空文件")
    filename = f"{current_user.id}-{uuid4().hex}{suffix}"
    (UPLOAD_ROOT / filename).write_bytes(content)
    return {"url": f"/uploads/community/{filename}", "media_type": media_type}


@router.get("/plaza", response_model=list[PlazaMessageOut])
def list_plaza_messages(
    limit: int = Query(default=60, ge=1, le=100),
    db: Session = Depends(get_sync_db),
):
    rows = (
        db.query(PlazaMessage, User.nickname)
        .join(User, User.id == PlazaMessage.user_id)
        .filter(PlazaMessage.status == "published")
        .order_by(PlazaMessage.created_at.desc(), PlazaMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [_plaza_out(message, nickname) for message, nickname in reversed(rows)]


@router.post("/plaza", response_model=PlazaMessageOut)
async def create_plaza_message(
    payload: PlazaMessageCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    _validate_media_urls(payload.image_url, payload.audio_url)
    moderation = moderate_content(db, payload.content)
    message = PlazaMessage(
        user_id=current_user.id,
        content=payload.content.strip(),
        image_url=payload.image_url,
        audio_url=payload.audio_url,
        status=moderation.status,
        moderation_reason=moderation.reason,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    result = _plaza_out(message, current_user.nickname)
    if message.status == "published":
        await plaza_connections.broadcast({"type": "plaza_message", "message": result})
    return result


@router.websocket("/plaza/ws")
async def plaza_websocket(websocket: WebSocket):
    await plaza_connections.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        plaza_connections.disconnect(websocket)
    except Exception:
        plaza_connections.disconnect(websocket)


@router.get("/{discussion_id}", response_model=DiscussionOut)
def get_discussion(
    discussion_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User | None = Depends(get_optional_user),
):
    obj = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    can_view_private = current_user and (current_user.id == obj.user_id or current_user.role == "admin") if obj else False
    if obj and (obj.status != "published" or obj.visibility != "公开") and not can_view_private:
        obj = None
    if not obj:
        raise HTTPException(status_code=404, detail="讨论不存在或正在审核")
    return obj


@router.post("/", response_model=DiscussionOut)
def create_discussion(
    payload: DiscussionCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    _validate_media_urls(payload.image_url, payload.audio_url)
    moderation = moderate_content(db, payload.title, payload.content)
    disc = Discussion(
        **payload.model_dump(exclude={"user_id"}),
        user_id=current_user.id,
        status=moderation.status,
        moderation_reason=moderation.reason,
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)
    return disc


@router.patch("/{discussion_id}", response_model=DiscussionOut)
def update_discussion(
    discussion_id: int,
    payload: DiscussionCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="讨论不存在")
    if obj.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权编辑该讨论")
    _validate_media_urls(payload.image_url, payload.audio_url)
    moderation = moderate_content(db, payload.title, payload.content)
    obj.title = payload.title
    obj.content = payload.content
    obj.image_url = payload.image_url
    obj.audio_url = payload.audio_url
    obj.category = payload.category
    obj.visibility = payload.visibility
    obj.status = moderation.status
    obj.moderation_reason = moderation.reason
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{discussion_id}")
def delete_discussion(
    discussion_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="讨论不存在")
    if obj.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除该讨论")
    db.query(DiscussionLike).filter(DiscussionLike.discussion_id == discussion_id).delete()
    db.query(Reply).filter(Reply.discussion_id == discussion_id).delete()
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/{discussion_id}/view")
def increment_view(discussion_id: int, db: Session = Depends(get_sync_db)):
    obj = db.query(Discussion).filter(
        Discussion.id == discussion_id,
        Discussion.status == "published",
        Discussion.visibility == "公开",
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="讨论不存在")
    obj.view_count = (obj.view_count or 0) + 1
    db.commit()
    return {"view_count": obj.view_count}


@router.post("/{discussion_id}/like")
def like_discussion(
    discussion_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.query(Discussion).filter(Discussion.id == discussion_id, Discussion.status == "published").first()
    if not obj:
        raise HTTPException(status_code=404, detail="讨论不存在")
    if obj.visibility != "公开" and obj.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="讨论不存在")
    existing = db.query(DiscussionLike).filter(
        DiscussionLike.discussion_id == discussion_id,
        DiscussionLike.user_id == current_user.id,
    ).first()
    if existing:
        db.delete(existing)
        obj.like_count = max(0, (obj.like_count or 0) - 1)
        liked = False
    else:
        db.add(DiscussionLike(discussion_id=discussion_id, user_id=current_user.id))
        obj.like_count = (obj.like_count or 0) + 1
        liked = True
    db.commit()
    return {"liked": liked, "like_count": obj.like_count}


@router.get("/{discussion_id}/replies", response_model=list[ReplyOut])
def list_replies(
    discussion_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User | None = Depends(get_optional_user),
):
    discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    can_view_private = current_user and (current_user.id == discussion.user_id or current_user.role == "admin") if discussion else False
    if not discussion or ((discussion.status != "published" or discussion.visibility != "公开") and not can_view_private):
        raise HTTPException(status_code=404, detail="讨论不存在或不可见")
    return db.query(Reply).filter(
        Reply.discussion_id == discussion_id,
        Reply.status == "published",
    ).order_by(Reply.created_at.asc()).all()


@router.post("/{discussion_id}/replies", response_model=ReplyOut)
def add_reply(
    discussion_id: int,
    payload: ReplyCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    disc = db.query(Discussion).filter(
        Discussion.id == discussion_id,
        Discussion.status == "published",
    ).first()
    if not disc:
        raise HTTPException(status_code=404, detail="讨论不存在")
    if disc.visibility != "公开" and disc.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="讨论不存在")
    moderation = moderate_content(db, payload.content)
    reply = Reply(
        discussion_id=discussion_id,
        user_id=current_user.id,
        content=payload.content,
        status=moderation.status,
    )
    db.add(reply)
    if moderation.status == "published":
        disc.reply_count = (disc.reply_count or 0) + 1
    db.commit()
    db.refresh(reply)
    return reply


@router.delete("/{discussion_id}/replies/{reply_id}")
def delete_reply(
    discussion_id: int,
    reply_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.query(Reply).filter(Reply.id == reply_id, Reply.discussion_id == discussion_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="回复不存在")
    if obj.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除该回复")
    disc = db.query(Discussion).filter(Discussion.id == discussion_id).first()
    if disc and obj.status == "published":
        disc.reply_count = max(0, (disc.reply_count or 0) - 1)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/{discussion_id}/reports")
def report_discussion(
    discussion_id: int,
    payload: ReportCreate,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    if not db.query(Discussion.id).filter(Discussion.id == discussion_id).first():
        raise HTTPException(status_code=404, detail="讨论不存在")
    duplicate = db.query(Report).filter(
        Report.reporter_id == current_user.id,
        Report.target_type == "discussion",
        Report.target_id == discussion_id,
        Report.status == "pending",
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="你已经举报过该内容")
    report = Report(
        reporter_id=current_user.id,
        target_type="discussion",
        target_id=discussion_id,
        reason=payload.reason,
        detail=payload.detail,
    )
    db.add(report)
    db.commit()
    return {"ok": True, "report_id": report.id, "status": report.status}
