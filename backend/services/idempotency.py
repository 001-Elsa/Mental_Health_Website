import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import IdempotencyRecord


class IdempotencyInProgress(Exception):
    pass


def begin_operation(
    db: Session,
    *,
    user_id: int,
    operation: str,
    key: str,
) -> tuple[IdempotencyRecord, dict[str, Any] | None]:
    existing = db.query(IdempotencyRecord).filter(
        IdempotencyRecord.user_id == user_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == key,
    ).first()
    if existing:
        if existing.status == "completed" and existing.response_json:
            return existing, json.loads(existing.response_json)
        updated_at = existing.updated_at or existing.created_at or datetime.utcnow()
        if datetime.utcnow() - updated_at < timedelta(minutes=5):
            raise IdempotencyInProgress
        existing.status = "processing"
        existing.response_json = ""
        db.commit()
        return existing, None

    record = IdempotencyRecord(
        user_id=user_id,
        operation=operation,
        idempotency_key=key,
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
        return record, None
    except IntegrityError:
        db.rollback()
        existing = db.query(IdempotencyRecord).filter(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == key,
        ).first()
        if existing and existing.status == "completed" and existing.response_json:
            return existing, json.loads(existing.response_json)
        raise IdempotencyInProgress


def complete_operation(db: Session, record: IdempotencyRecord, response: dict[str, Any]) -> None:
    record.status = "completed"
    record.response_json = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    record.updated_at = datetime.utcnow()
    db.commit()

