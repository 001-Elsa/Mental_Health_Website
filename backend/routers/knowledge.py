from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_optional_user, require_admin
from backend.services.audit import record_audit
from backend.services.rag import answer_with_knowledge, retrieve
from database.database import get_sync_db
from database.models import KnowledgeDocument, User

router = APIRouter(prefix="/api/knowledge", tags=["RAG知识库"])


class KnowledgeAsk(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=2, max_length=256)
    source: str = Field(default="", max_length=256)
    category: str = Field(default="心理科普", max_length=64)
    content: str = Field(min_length=20)


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=200),
    db: Session = Depends(get_sync_db),
):
    return [chunk.__dict__ for chunk in retrieve(db, q)]


@router.post("/ask")
async def ask(
    payload: KnowledgeAsk,
    db: Session = Depends(get_sync_db),
    current_user: User | None = Depends(get_optional_user),
):
    answer, chunks, personalization = await answer_with_knowledge(
        db,
        payload.question.strip(),
        user_id=current_user.id if current_user else None,
    )
    return {
        "answer": answer,
        "personalization": personalization,
        "citations": [
            {"id": chunk.id, "title": chunk.title, "source": chunk.source, "score": round(chunk.score, 4)}
            for chunk in chunks
        ],
    }


@router.post("/documents")
def create_document(
    payload: KnowledgeCreate,
    request: Request,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(require_admin),
):
    document = KnowledgeDocument(**payload.model_dump())
    db.add(document)
    db.flush()
    record_audit(
        db,
        actor_id=current_user.id,
        action="knowledge_document.create",
        target_type="knowledge_document",
        target_id=document.id,
        detail={"title": document.title, "source": document.source},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    db.refresh(document)
    return document
