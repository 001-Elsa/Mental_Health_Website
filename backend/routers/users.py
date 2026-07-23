import json
import random
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.auth import get_current_user, hash_password, verify_password
from backend.core.time import utc_now
from backend.core.config import get_settings
from backend.repositories import users
from backend.services.cache import cache_service
from database.database import get_sync_db
from database.models import RefreshToken, User, UserNotification, UserProfile
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/users", tags=["用户"])

PROFILE_UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "profile"
PROFILE_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
PROFILE_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class ProfileUpdateReq(BaseModel):
    nickname: str = Field(min_length=2, max_length=20)
    signature: str = Field(default="", max_length=120)


class PasswordChangeReq(BaseModel):
    current_password: str = Field(min_length=6, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class PhoneChangeReq(BaseModel):
    new_phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    code: str = Field(min_length=4, max_length=6)
    current_password: str = Field(min_length=6, max_length=72)


class EmailCodeReq(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    current_password: str = Field(min_length=6, max_length=72)


class EmailBindReq(EmailCodeReq):
    code: str = Field(min_length=4, max_length=6)


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", email):
        raise HTTPException(status_code=422, detail="请输入有效邮箱")
    return email


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "phone": user.phone,
        "email": user.email or "",
        "avatar_url": user.avatar_url,
        "background_url": user.background_url,
        "signature": user.signature,
        "role": user.role,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _looks_like_image(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return _user_payload(current_user)


@router.patch("/me")
def update_me(
    payload: ProfileUpdateReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    nickname = payload.nickname.strip()
    duplicate = users.get_by_nickname(db, nickname)
    if duplicate and duplicate.id != current_user.id:
        raise HTTPException(status_code=409, detail="该昵称已被占用")
    current_user.nickname = nickname
    current_user.username = nickname
    current_user.signature = payload.signature.strip()
    db.commit()
    db.refresh(current_user)
    return _user_payload(current_user)


@router.post("/me/media")
async def upload_profile_media(
    kind: str = Query(pattern=r"^(avatar|background)$"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    suffix = PROFILE_IMAGE_TYPES.get(content_type)
    if not suffix:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG 或 WebP 图片")
    max_bytes = 3 * 1024 * 1024 if kind == "avatar" else 8 * 1024 * 1024
    content = await file.read(max_bytes + 1)
    await file.close()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"图片不能超过 {max_bytes // (1024 * 1024)}MB")
    if not _looks_like_image(content, content_type):
        raise HTTPException(status_code=422, detail="图片内容与文件格式不匹配")
    filename = f"{current_user.id}-{kind}-{uuid4().hex}{suffix}"
    (PROFILE_UPLOAD_ROOT / filename).write_bytes(content)
    url = f"/uploads/profile/{filename}"
    if kind == "avatar":
        current_user.avatar_url = url
    else:
        current_user.background_url = url
    db.commit()
    db.refresh(current_user)
    return {"url": url, "kind": kind, "user": _user_payload(current_user)}


@router.post("/me/password")
def change_password(
    payload: PasswordChangeReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    current_user.password_hash = hash_password(payload.new_password)
    current_user.token_version += 1
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": utc_now()}, synchronize_session=False)
    db.commit()
    return {"ok": True, "message": "密码已更新，请重新登录"}


@router.post("/me/phone")
def change_phone(
    payload: PhoneChangeReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if payload.new_phone == current_user.phone:
        raise HTTPException(status_code=400, detail="新手机号不能与当前手机号相同")
    duplicate = users.get_by_phone(db, payload.new_phone)
    if duplicate and duplicate.id != current_user.id:
        raise HTTPException(status_code=409, detail="该手机号已被其他账号使用")
    if cache_service.get_code(payload.new_phone) != payload.code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    current_user.phone = payload.new_phone
    cache_service.delete_code(payload.new_phone)
    db.commit()
    db.refresh(current_user)
    return _user_payload(current_user)


@router.post("/me/email-code")
def send_email_code(
    payload: EmailCodeReq,
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    email = _normalize_email(payload.email)
    rate_key = f"rate:email:{current_user.id}:{email}"
    if cache_service.increment(rate_key, 60) > 5:
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")
    code = str(random.randint(1000, 9999))
    settings = get_settings()
    if settings.email_webhook_url:
        body = json.dumps({"email": email, "code": code, "subject": "心晴 Campus 邮箱验证码"}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(settings.email_webhook_url, data=body, method="POST")
        request.add_header("Content-Type", "application/json; charset=utf-8")
        if settings.email_webhook_token:
            request.add_header("Authorization", "Bearer " + settings.email_webhook_token)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 400:
                    raise HTTPException(status_code=502, detail="邮件服务发送失败")
        except HTTPException:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            raise HTTPException(status_code=502, detail="邮件服务连接失败，请稍后重试")
    elif settings.environment != "development":
        raise HTTPException(status_code=503, detail="邮件服务尚未配置")
    cache_key = f"email_code:{current_user.id}:{email}"
    cache_service.set(cache_key, code, 300)
    result = {"ok": True, "message": "验证码已发送"}
    if not settings.email_webhook_url:
        result["dev_code"] = code
        result["message"] = "本地开发模式验证码已生成"
    return result


@router.post("/me/email")
def bind_email(
    payload: EmailBindReq,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    email = _normalize_email(payload.email)
    duplicate = users.get_by_email(db, email)
    if duplicate and duplicate.id != current_user.id:
        raise HTTPException(status_code=409, detail="该邮箱已被其他账号绑定")
    cache_key = f"email_code:{current_user.id}:{email}"
    if cache_service.get(cache_key) != payload.code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    current_user.email = email
    cache_service.delete(cache_key)
    db.commit()
    db.refresh(current_user)
    return _user_payload(current_user)


@router.get("/me/profile")
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    return {
        "summary": profile.summary if profile else "还没有足够的对话生成支持画像。",
        "dominant_emotions": profile.dominant_emotions.split("、") if profile and profile.dominant_emotions else [],
        "recommendation_emotion": profile.recommendation_emotion if profile else "",
        "stressors": profile.stressors.split("、") if profile and profile.stressors else [],
        "coping_preferences": profile.coping_preferences.split("、") if profile and profile.coping_preferences else [],
        "updated_at": profile.updated_at if profile else None,
    }


@router.get("/me/notifications")
def list_my_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    query = db.query(UserNotification).filter(UserNotification.user_id == current_user.id)
    if unread_only:
        query = query.filter(UserNotification.read_at.is_(None))
    rows = query.order_by(UserNotification.created_at.desc(), UserNotification.id.desc()).limit(limit).all()
    unread_count = db.query(UserNotification.id).filter(
        UserNotification.user_id == current_user.id,
        UserNotification.read_at.is_(None),
    ).count()
    return {"unread_count": unread_count, "items": rows}


@router.patch("/me/notifications/{notification_id}/read")
def read_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    notification = db.query(UserNotification).filter(
        UserNotification.id == notification_id,
        UserNotification.user_id == current_user.id,
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    if notification.read_at is None:
        notification.read_at = utc_now()
        db.commit()
    return {"ok": True, "read_at": notification.read_at}


@router.patch("/me/notifications/read-all")
def read_all_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_sync_db),
):
    updated = db.query(UserNotification).filter(
        UserNotification.user_id == current_user.id,
        UserNotification.read_at.is_(None),
    ).update({"read_at": utc_now()}, synchronize_session=False)
    db.commit()
    return {"ok": True, "updated": updated}
