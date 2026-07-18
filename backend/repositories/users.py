from sqlalchemy.orm import Session

from database.models import User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_by_nickname(db: Session, nickname: str) -> User | None:
    return db.query(User).filter(User.nickname == nickname).first()


def get_by_phone(db: Session, phone: str) -> User | None:
    return db.query(User).filter(User.phone == phone).first()


def get_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, *, nickname: str, phone: str, password_hash: str) -> User:
    user = User(username=nickname, nickname=nickname, phone=phone, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
