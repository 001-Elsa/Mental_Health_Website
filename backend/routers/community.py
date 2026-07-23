import asyncio
import re
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import create_websocket_token, decode_access_token, get_current_user, get_optional_user
from backend.core.config import get_settings
from backend.schemas import DiscussionCreate, DiscussionOut, PlazaMessageCreate, PlazaMessageOut, ReplyCreate, ReplyOut
from backend.services.content_moderation import moderate_content
from database.database import SyncSessionLocal, get_sync_db
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
IMAGE_SUFFIXES = {".jpg", ".png", ".webp", ".gif"}
AUDIO_SUFFIXES = {".webm", ".ogg", ".mp3", ".wav", ".m4a", ".aac"}
UPLOAD_NAME_RE = re.compile(r"^(?P<user_id>\d+)-[0-9a-f]{32}(?P<suffix>\.[a-z0-9]+)$")


def _valid_signature(content_type: str, header: bytes) -> bool:
    checks = {
        "image/jpeg": header.startswith(b"\xff\xd8\xff"),
        "image/png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
        "image/gif": header.startswith((b"GIF87a", b"GIF89a")),
        "audio/webm": header.startswith(b"\x1a\x45\xdf\xa3"),
        "audio/ogg": header.startswith(b"OggS"),
        "audio/mpeg": header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0),
        "audio/wav": header.startswith(b"RIFF") and header[8:12] == b"WAVE",
        "audio/mp4": len(header) >= 12 and header[4:8] == b"ftyp",
        "audio/aac": len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0,
    }
    return checks.get(content_type, False)


class PlazaConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()
        self.connections_by_ip: Counter[str] = Counter()

    async def connect(self, websocket: WebSocket, ip: str) -> bool:
        settings = get_settings()
        if len(self.connections) >= settings.websocket_max_connections or self.connections_by_ip[ip] >= settings.websocket_max_connections_per_ip:
            await websocket.close(code=1013, reason="Too many connections")
            return False
        await websocket.accept()
        self.connections.add(websocket)
        self.connections_by_ip[ip] += 1
        return True

    def disconnect(self, websocket: WebSocket, ip: str):
        if websocket in self.connections:
            self.connections.discard(websocket)
            self.connections_by_ip[ip] -= 1
            if self.connections_by_ip[ip] <= 0:
                self.connections_by_ip.pop(ip, None)

    async def broadcast(self, payload: dict):
        stale: list[WebSocket] = []
        for websocket in tuple(self.connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            ip = websocket.client.host if websocket.client else "unknown"
            self.disconnect(websocket, ip)


plaza_connections = PlazaConnectionManager()


def _validate_media_urls(
    db: Session,
    user: User,
    image_url: str,
    audio_url: str,
    *,
    exclude_discussion_id: int | None = None,
) -> None:
    for value, expected_suffixes in ((image_url, IMAGE_SUFFIXES), (audio_url, AUDIO_SUFFIXES)):
        if not value:
            continue
        prefix = "/uploads/community/"
        filename = value.removeprefix(prefix)
        match = UPLOAD_NAME_RE.fullmatch(filename) if value.startswith(prefix) else None
        if not match or int(match.group("user_id")) != user.id or match.group("suffix") not in expected_suffixes:
            raise HTTPException(status_code=422, detail="媒体地址无效或不属于当前用户")
        if not (UPLOAD_ROOT / filename).is_file():
            raise HTTPException(status_code=422, detail="媒体文件不存在")
        discussion_query = db.query(Discussion).filter(
            (Discussion.image_url == value) | (Discussion.audio_url == value)
        )
        if exclude_discussion_id is not None:
            discussion_query = discussion_query.filter(Discussion.id != exclude_discussion_id)
        in_plaza = db.query(PlazaMessage.id).filter(
            (PlazaMessage.image_url == value) | (PlazaMessage.audio_url == value)
        ).first()
        if discussion_query.first() or in_plaza:
            raise HTTPException(status_code=409, detail="媒体文件已被其他内容使用")


def _remove_media(*urls: str) -> None:
    for value in urls:
        if value.startswith("/uploads/community/"):
            path = UPLOAD_ROOT / value.rsplit("/", 1)[-1]
            if path.parent == UPLOAD_ROOT and path.is_file():
                path.unlink(missing_ok=True)


def _cleanup_orphan_uploads(user_id: int, *, limit: int = 20) -> None:
    cutoff = time.time() - 24 * 3600
    checked = 0
    with SyncSessionLocal() as db:
        for path in UPLOAD_ROOT.iterdir():
            if checked >= limit or not path.is_file() or not path.name.startswith(f"{user_id}-") or path.stat().st_mtime >= cutoff:
                continue
            checked += 1
            url = f"/uploads/community/{path.name}"
            used = db.query(Discussion.id).filter((Discussion.image_url == url) | (Discussion.audio_url == url)).first()
            used = used or db.query(PlazaMessage.id).filter((PlazaMessage.image_url == url) | (PlazaMessage.audio_url == url)).first()
            if not used:
                path.unlink(missing_ok=True)


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
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    media = MEDIA_TYPES.get(content_type)
    if not media:
        raise HTTPException(status_code=415, detail="仅支持常见图片或音频格式")
    media_type, suffix, max_bytes = media
    filename = f"{current_user.id}-{uuid4().hex}{suffix}"
    destination = UPLOAD_ROOT / filename
    temporary = destination.with_suffix(destination.suffix + ".part")
    total = 0
    header = b""
    try:
        with temporary.open("xb") as target:
            while chunk := await file.read(64 * 1024):
                if not header:
                    header = chunk[:64]
                    if not _valid_signature(content_type, header):
                        raise HTTPException(status_code=415, detail="文件内容与声明的媒体格式不一致")
                total += len(chunk)
                if total > max_bytes:
                    limit_mb = max_bytes // (1024 * 1024)
                    raise HTTPException(status_code=413, detail=f"文件不能超过 {limit_mb}MB")
                await asyncio.to_thread(target.write, chunk)
        if not total:
            raise HTTPException(status_code=422, detail="不能上传空文件")
        temporary.replace(destination)
    finally:
        await file.close()
        temporary.unlink(missing_ok=True)
    await asyncio.to_thread(_cleanup_orphan_uploads, current_user.id)
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
    _validate_media_urls(db, current_user, payload.image_url, payload.audio_url)
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
    ticket = websocket.query_params.get("ticket", "")
    claims = decode_access_token(ticket)
    if not claims or claims.get("type") != "websocket":
        await websocket.close(code=1008, reason="Authentication required")
        return
    with SyncSessionLocal() as db:
        user = db.query(User).filter(User.id == int(claims.get("user_id", 0))).first()
        if not user or user.token_version != int(claims.get("ver", -1)):
            await websocket.close(code=1008, reason="Authentication required")
            return
    ip = websocket.client.host if websocket.client else "unknown"
    if not await plaza_connections.connect(websocket, ip):
        return
    try:
        while True:
            await asyncio.wait_for(websocket.receive_text(), timeout=get_settings().websocket_idle_timeout_seconds)
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        await websocket.close(code=1001)
    except Exception:
        await websocket.close(code=1011)
    finally:
        plaza_connections.disconnect(websocket, ip)


@router.post("/plaza/ws-ticket")
def create_plaza_ws_ticket(current_user: User = Depends(get_current_user)):
    return {"ticket": create_websocket_token(user_id=current_user.id, token_version=current_user.token_version)}


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
    _validate_media_urls(db, current_user, payload.image_url, payload.audio_url)
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
    _validate_media_urls(db, current_user, payload.image_url, payload.audio_url, exclude_discussion_id=obj.id)
    old_media = (obj.image_url, obj.audio_url)
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
    _remove_media(*(url for url in old_media if url not in {obj.image_url, obj.audio_url}))
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
    _remove_media(obj.image_url, obj.audio_url)
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
