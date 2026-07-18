import json
from typing import Any

from sqlalchemy.orm import Session

from database.models import AdminAuditLog


def record_audit(
    db: Session,
    *,
    actor_id: int,
    action: str,
    target_type: str,
    target_id: int | str = "",
    detail: dict[str, Any] | str | None = None,
    request_id: str = "",
) -> AdminAuditLog:
    if isinstance(detail, dict):
        detail_text = json.dumps(detail, ensure_ascii=False, sort_keys=True)
    else:
        detail_text = detail or ""
    log = AdminAuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        detail=detail_text,
        request_id=request_id,
    )
    db.add(log)
    return log

