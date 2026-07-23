import json
import hashlib
import ipaddress
import re
import secrets
import urllib.error
import urllib.request
from datetime import datetime
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database.database import get_sync_db
from backend.repositories import users
from backend.core.config import get_settings
from backend.core.time import utc_now
from backend.services.cache import cache_service
from backend.services.auth_service import register_user, login_user
from backend.auth import create_access_token, create_refresh_token, decode_access_token
from database.models import RefreshToken, User

router = APIRouter(prefix="/api/auth", tags=["用户认证"])


# ====== Schema ======
class SendCodeReq(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")


class RegisterReq(BaseModel):
    nickname: str = Field(min_length=2, max_length=20)
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    code: str = Field(min_length=4, max_length=6)
    password: str = Field(min_length=6, max_length=72)


class LoginReq(BaseModel):
    nickname: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=6, max_length=72)
    remember_me: bool = False


class RefreshReq(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=32, max_length=4096)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issue_refresh_token(db: Session, user: User) -> str:
    token, expires_at = create_refresh_token(user_id=user.id, token_version=user.token_version)
    db.add(RefreshToken(user_id=user.id, token_hash=_token_hash(token), expires_at=expires_at))
    return token


def _set_refresh_cookie(response: Response, token: str, *, persistent: bool = True) -> None:
    settings = get_settings()
    response.set_cookie(
        key="mh_refresh",
        value=token,
        max_age=settings.refresh_token_expire_days * 86400 if persistent else None,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/api/auth",
    )


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    forwarded = request.headers.get("X-Real-IP", "")
    try:
        peer_is_proxy = ipaddress.ip_address(peer).is_private or ipaddress.ip_address(peer).is_loopback
        if peer_is_proxy and forwarded:
            return str(ipaddress.ip_address(forwarded))
    except ValueError:
        pass
    return peer or "unknown"


# ====== API ======
@router.post("/send-code")
def send_code(payload: SendCodeReq):
    """发送短信验证码。

    未配置短信网关时走本地开发模式，把验证码返回给前端，保证注册流程可用。
    生产环境配置 SMS_WEBHOOK_URL 后不会返回验证码。
    """
    phone = payload.phone.strip()
    if cache_service.increment(f"rate:sms:{phone}", 60) > 5:
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="请输入有效的手机号")

    code = f"{secrets.randbelow(1_000_000):06d}"
    sms_configured = bool(get_settings().sms_webhook_url)
    if not sms_configured and get_settings().environment != "development":
        raise HTTPException(status_code=503, detail="短信服务尚未配置")
    if sms_configured:
        send_sms_code(phone, code)
    cache_service.set_code(phone, code)
    result = {"ok": True, "phone": phone, "message": "验证码已发送"}
    if not sms_configured:
        result["dev_code"] = code
        result["message"] = "本地开发模式验证码已生成"
    return result


def send_sms_code(phone: str, code: str) -> None:
    """通过短信网关发送验证码。

    配置环境变量:
    - SMS_WEBHOOK_URL: 你的短信服务 HTTP 地址
    - SMS_WEBHOOK_TOKEN: 可选，Bearer Token
    - SMS_SIGN_NAME: 可选，短信签名
    """
    settings = get_settings()
    webhook_url = settings.sms_webhook_url
    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail="短信服务未配置，请先设置 SMS_WEBHOOK_URL 后再发送验证码",
        )

    payload = {
        "phone": phone,
        "code": code,
        "sign_name": settings.sms_sign_name,
        "message": f"您的验证码是 {code}，5分钟内有效。请勿泄露给他人。",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if settings.sms_webhook_token:
        req.add_header("Authorization", "Bearer " + settings.sms_webhook_token)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                raise HTTPException(status_code=502, detail="短信网关发送失败")
    except HTTPException:
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPException(status_code=502, detail="短信网关连接失败，请稍后重试")


@router.post("/register")
def register(payload: RegisterReq, request: Request, db: Session = Depends(get_sync_db)):
    """注册新用户"""
    phone = payload.phone.strip()
    code = payload.code.strip()

    # 校验验证码
    saved_code = cache_service.get_code(phone)
    attempt_key = f"rate:register_code:{phone}:{_client_ip(request)}"
    if cache_service.increment(attempt_key, 10 * 60) > 6:
        raise HTTPException(status_code=429, detail="验证码尝试次数过多，请稍后重试")
    if not saved_code or not secrets.compare_digest(saved_code, code):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 检查昵称是否已被占用
    if users.get_by_nickname(db, payload.nickname):
        raise HTTPException(status_code=400, detail="该昵称已被占用")

    # 检查手机是否已被注册
    if users.get_by_phone(db, phone):
        raise HTTPException(status_code=400, detail="该手机号已被注册")

    user = register_user(db, nickname=payload.nickname, phone=phone, password=payload.password)
    # 清除验证码
    cache_service.delete_code(phone)
    cache_service.delete(attempt_key)

    return {"ok": True, "user_id": user.id, "nickname": user.nickname}


@router.post("/login")
def login(payload: LoginReq, request: Request, response: Response, db: Session = Depends(get_sync_db)):
    nickname = payload.nickname.strip().lower()
    ip = _client_ip(request)
    pair_key = f"rate:login_pair:{nickname}:{ip}"
    ip_key = f"rate:login_ip:{ip}"
    if int(cache_service.get(pair_key) or 0) >= 8 or int(cache_service.get(ip_key) or 0) >= 40:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后再试")
    result = login_user(db, nickname=payload.nickname, password=payload.password)
    if not result:
        cache_service.increment(pair_key, 15 * 60)
        cache_service.increment(ip_key, 15 * 60)
        raise HTTPException(status_code=401, detail="昵称或密码错误")
    user, token = result
    cache_service.delete(pair_key)
    refresh_token = _issue_refresh_token(db, user)
    db.commit()
    _set_refresh_cookie(response, refresh_token, persistent=payload.remember_me)

    return {
        "ok": True,
        "token": token,
        "access_token": token,
        "expires_in": get_settings().access_token_expire_minutes * 60,
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "phone": user.phone,
            "email": user.email or "",
            "avatar_url": user.avatar_url,
            "background_url": user.background_url,
            "signature": user.signature,
            "role": user.role,
            "created_at": user.created_at,
        },
    }


@router.post("/refresh")
def refresh_tokens(
    response: Response,
    payload: RefreshReq | None = None,
    mh_refresh: str | None = Cookie(default=None),
    db: Session = Depends(get_sync_db),
):
    refresh_token = mh_refresh or (payload.refresh_token if payload else None)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="缺少刷新令牌")
    claims = decode_access_token(refresh_token)
    if not claims or claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="刷新令牌无效")
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _token_hash(refresh_token)
    ).first()
    if not record or record.revoked_at or record.expires_at <= utc_now():
        raise HTTPException(status_code=401, detail="刷新令牌已失效或被撤销")
    user = db.query(User).filter(User.id == int(claims.get("user_id", 0))).first()
    if not user or int(claims.get("ver", -1)) != user.token_version or user.id != record.user_id:
        raise HTTPException(status_code=401, detail="刷新令牌已失效")
    new_refresh = _issue_refresh_token(db, user)
    record.revoked_at = utc_now()
    record.replaced_by_hash = _token_hash(new_refresh)
    access = create_access_token({"user_id": user.id, "nickname": user.nickname, "ver": user.token_version})
    db.commit()
    _set_refresh_cookie(response, new_refresh, persistent=False)
    return {
        "token": access,
        "access_token": access,
        "expires_in": get_settings().access_token_expire_minutes * 60,
    }


@router.post("/logout")
def logout(
    response: Response,
    payload: RefreshReq | None = None,
    mh_refresh: str | None = Cookie(default=None),
    db: Session = Depends(get_sync_db),
):
    refresh_token = mh_refresh or (payload.refresh_token if payload else None)
    response.delete_cookie("mh_refresh", path="/api/auth")
    if not refresh_token:
        return {"ok": True}
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _token_hash(refresh_token),
        RefreshToken.revoked_at.is_(None),
    ).first()
    if record:
        record.revoked_at = utc_now()
        db.commit()
    return {"ok": True}
