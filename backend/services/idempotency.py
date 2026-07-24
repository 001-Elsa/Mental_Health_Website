import json
import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import IdempotencyRecord
from backend.core.time import utc_now


class IdempotencyInProgress(Exception):
    pass


class IdempotencyKeyReuse(Exception):
    """The caller reused an idempotency key for another request body."""


def fingerprint_request(payload: Any) -> str:
    """Return a stable, non-reversible representation of a request payload."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def begin_operation(
    db: Session,
    *,
    user_id: int,
    operation: str,
    key: str,
    request_fingerprint: str,
) -> tuple[IdempotencyRecord, dict[str, Any] | None]:
    existing = db.query(IdempotencyRecord).filter(
        IdempotencyRecord.user_id == user_id,
        IdempotencyRecord.operation == operation,
        IdempotencyRecord.idempotency_key == key,
    ).first()
    if existing:
        if existing.request_fingerprint and existing.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyReuse
        # Records created before request fingerprints existed are deliberately
        # not replayed.  Reusing a legacy key is ambiguous and should be retried
        # with a fresh key instead of returning a potentially wrong response.
        if not existing.request_fingerprint:
            raise IdempotencyKeyReuse
        if existing.status == "completed" and existing.response_json:
            return existing, json.loads(existing.response_json)
        updated_at = existing.updated_at or existing.created_at or utc_now()
        if utc_now() - updated_at < timedelta(minutes=5):
            raise IdempotencyInProgress
        existing.status = "processing"
        existing.response_json = ""
        db.commit()
        return existing, None

    record = IdempotencyRecord(
        user_id=user_id,
        operation=operation,
        idempotency_key=key,
        request_fingerprint=request_fingerprint,
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
        if existing and existing.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyReuse
        if existing and existing.status == "completed" and existing.response_json:
            return existing, json.loads(existing.response_json)
        raise IdempotencyInProgress


def complete_operation(db: Session, record: IdempotencyRecord, response: dict[str, Any]) -> None:
    record.status = "completed"
    record.response_json = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    record.updated_at = utc_now()
    db.commit()
