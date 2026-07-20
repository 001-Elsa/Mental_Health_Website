from sqlalchemy.orm import Session

from backend.auth import hash_password, verify_password, create_access_token
from backend.repositories import users
from database.models import User


def register_user(db: Session, *, nickname: str, phone: str, password: str) -> User:
    return users.create_user(
        db,
        nickname=nickname,
        phone=phone,
        password_hash=hash_password(password),
    )


def login_user(db: Session, *, nickname: str, password: str) -> tuple[User, str] | None:
    user = users.get_by_nickname(db, nickname)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user, create_access_token({
        "user_id": user.id,
        "nickname": user.nickname,
        "ver": user.token_version,
    })
