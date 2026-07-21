from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import get_optional_user, require_admin
from backend.services.audit import record_audit
from backend.services.rag import RetrievedChunk, answer_with_knowledge, retrieve
from database.database import get_sync_db
from database.models import KnowledgeDocument, User

router = APIRouter(prefix="/api/knowledge", tags=["RAG 知识库"])


class KnowledgeAsk(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=2, max_length=256)
    source: str = Field(default="", max_length=256)
    category: str = Field(default="心理科普", max_length=64)
    content: str = Field(min_length=20)


def _source_type(chunk: RetrievedChunk) -> str:
    if chunk.kind == "own_conversation":
        return "own_history"
    if chunk.kind == "public_conversation":
        return "public_conversation"
    return "reviewed_knowledge"


def _citation(chunk: RetrievedChunk) -> dict:
    return {
        "id": chunk.id,
        "title": chunk.title,
        "source": chunk.source,
        "score": round(chunk.score, 4),
        "source_type": _source_type(chunk),
        "kind": chunk.kind,
    }


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=200),
    db: Session = Depends(get_sync_db),
):
    return [_citation(chunk) for chunk in retrieve(db, q)]


@router.post("/ask")
async def ask(
    payload: KnowledgeAsk,
    db: Session = Depends(get_sync_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await answer_with_knowledge(
        db,
        payload.question.strip(),
        user_id=current_user.id if current_user else None,
    )
    reviewed_sources = [_citation(chunk) for chunk in result.knowledge_chunks]
    context_sources = [_citation(chunk) for chunk in result.conversation_chunks]
    return {
        "answer": result.answer,
        "grounded": result.grounded,
        "refusal_reason": result.refusal_reason,
        "personalization": result.personalization,
        "source_summary": {
            "reviewed_knowledge": len(reviewed_sources),
            "own_history": result.personalization["own_history"],
            "public_conversations": result.personalization["public_conversations"],
        },
        "citations": reviewed_sources,
        "context_sources": context_sources,
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
