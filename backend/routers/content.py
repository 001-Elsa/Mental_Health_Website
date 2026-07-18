from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.schemas import PublicConversationOut
from backend.services.content_search import period_start
from database.database import get_sync_db
from database.models import Consultation

router = APIRouter(prefix="/api/content", tags=["心理内容"])


@router.get("/public-conversations", response_model=list[PublicConversationOut])
def list_public_conversations(
    keyword: str = Query(default="", max_length=80),
    period: str = Query(default="all"),
    db: Session = Depends(get_sync_db),
):
    query = db.query(Consultation).filter(Consultation.visibility == "公开")
    clean_keyword = keyword.strip()
    if clean_keyword:
        query = query.filter(Consultation.title.contains(clean_keyword))
    since = period_start(period)
    if since is not None:
        query = query.filter(Consultation.created_at >= since)
    return query.order_by(Consultation.created_at.desc()).all()
