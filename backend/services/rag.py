import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.services.ai_client import ai_client
from backend.services.risk_engine import assess_risk
from database.models import Article, ChatMessage, Consultation, KnowledgeDocument


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    title: str
    source: str
    content: str
    score: float
    kind: str = "knowledge"


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", lowered)
    chinese = [token for token in words if "\u4e00" <= token <= "\u9fff"]
    bigrams = ["".join(chinese[index:index + 2]) for index in range(len(chinese) - 1)]
    return words + bigrams


def _score(query_tokens: list[str], text: str) -> float:
    document_tokens = _tokens(text)
    if not document_tokens:
        return 0.0
    counts = Counter(document_tokens)
    length_norm = 1 + math.log(len(document_tokens))
    return sum((1 + math.log(counts[token])) for token in set(query_tokens) if counts[token]) / length_norm


def retrieve(db: Session, query: str, limit: int = 4) -> list[RetrievedChunk]:
    candidates: list[RetrievedChunk] = []
    query_tokens = _tokens(query)
    for document in db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "published").all():
        score = _score(query_tokens, f"{document.title} {document.category} {document.content}")
        if score > 0:
            candidates.append(RetrievedChunk(f"knowledge:{document.id}", document.title, document.source, document.content, score))
    for article in db.query(Article).filter(Article.status == "已发布").all():
        score = _score(query_tokens, f"{article.title} {article.category} {article.summary} {article.content}")
        if score > 0:
            candidates.append(RetrievedChunk(
                f"article:{article.id}",
                article.title,
                article.source_name or article.author,
                article.content or article.summary,
                score,
            ))
    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    if not ranked:
        return []
    threshold = max(0.12, ranked[0].score * 0.25)
    return [item for item in ranked if item.score >= threshold][:limit]


def _anonymize(text: str) -> str:
    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[已隐藏联系方式]", text)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[已隐藏邮箱]", value)
    value = re.sub(r"(?:微信|vx|qq)\s*[:：]?\s*[A-Za-z0-9_-]{5,}", "[已隐藏联系方式]", value, flags=re.I)
    return value


def retrieve_conversation_context(
    db: Session,
    query: str,
    *,
    user_id: int | None,
    own_limit: int = 2,
    public_limit: int = 3,
) -> list[RetrievedChunk]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    scoped_rows: list[tuple[Consultation, str]] = []
    if user_id is not None:
        own_rows = (
            db.query(Consultation)
            .filter(Consultation.user_id == user_id)
            .order_by(Consultation.last_message_at.desc(), Consultation.created_at.desc())
            .limit(60)
            .all()
        )
        scoped_rows.extend((row, "own_conversation") for row in own_rows)

    public_query = db.query(Consultation).filter(Consultation.visibility == "公开")
    if user_id is not None:
        public_query = public_query.filter(Consultation.user_id != user_id)
    public_rows = (
        public_query
        .order_by(Consultation.last_message_at.desc(), Consultation.created_at.desc())
        .limit(100)
        .all()
    )
    scoped_rows.extend((row, "public_conversation") for row in public_rows)

    conversation_ids = {row.conversation_id for row, _ in scoped_rows if row.conversation_id}
    grouped_messages: dict[str, list[ChatMessage]] = {conversation_id: [] for conversation_id in conversation_ids}
    if conversation_ids:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id.in_(conversation_ids))
            .order_by(ChatMessage.created_at.desc())
            .limit(1200)
            .all()
        )
        for message in reversed(messages):
            grouped_messages.setdefault(message.conversation_id, []).append(message)

    candidates: list[RetrievedChunk] = []
    for consultation, kind in scoped_rows:
        recent_messages = grouped_messages.get(consultation.conversation_id, [])[-10:]
        transcript = "\n".join(
            f"{'学生' if message.role == 'user' else 'AI'}：{message.content[:260]}"
            for message in recent_messages
        )
        searchable = " ".join((consultation.title, consultation.summary, consultation.memory_summary, transcript))
        score = _score(query_tokens, searchable)
        if score <= 0:
            continue
        is_own = kind == "own_conversation"
        candidates.append(RetrievedChunk(
            id=f"{kind}:{consultation.id}",
            title="与你过往经历相关的倾听记录" if is_own else "同学公开分享的相关经历",
            source="你的历史倾听" if is_own else "匿名公开倾听",
            content=_anonymize(searchable[:2600]),
            score=score,
            kind=kind,
        ))

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    own_chunks = [item for item in ranked if item.kind == "own_conversation"][:own_limit]
    public_chunks = [item for item in ranked if item.kind == "public_conversation"][:public_limit]
    return own_chunks + public_chunks


async def answer_with_knowledge(
    db: Session,
    question: str,
    *,
    user_id: int | None = None,
) -> tuple[str, list[RetrievedChunk], dict[str, int]]:
    assessment = assess_risk(question)
    if assessment.requires_intervention:
        return await ai_client.chat([], question, assessment), [], {"own_history": 0, "public_conversations": 0}

    knowledge_chunks = retrieve(db, question)
    conversation_chunks = retrieve_conversation_context(db, question, user_id=user_id)
    personalization = {
        "own_history": sum(chunk.kind == "own_conversation" for chunk in conversation_chunks),
        "public_conversations": sum(chunk.kind == "public_conversation" for chunk in conversation_chunks),
    }
    if not knowledge_chunks and not conversation_chunks:
        return (
            "知识库和相关倾听记录中暂时没有足够信息。你可以换一种说法，或咨询学校心理中心。",
            [],
            personalization,
        )
    if not get_settings().deepseek_api_key:
        if knowledge_chunks:
            excerpt = knowledge_chunks[0].content[:260].strip()
            return f"根据《{knowledge_chunks[0].title}》：{excerpt}", knowledge_chunks, personalization
        return (
            "我找到了与你问题相关的倾听记录，但当前 AI 服务未启用，暂时无法安全地综合生成个性化建议。",
            [],
            personalization,
        )

    knowledge_context = "\n\n".join(
        f"资料 {index + 1}｜{chunk.title}｜来源：{chunk.source}\n{chunk.content[:1200]}"
        for index, chunk in enumerate(knowledge_chunks)
    ) or "没有检索到可引用的审核资料。"
    conversation_context = "\n\n".join(
        f"{chunk.source}（仅用于归纳，不可直接引用）\n{chunk.content}"
        for chunk in conversation_chunks
    ) or "没有检索到相关倾听记录。"
    prompt = (
        "请为高校学生生成量身定做的心理支持回答，不做医疗诊断。\n"
        "你可以引用‘审核资料’，并在对应句末用[1][2]标注；资料不足时必须说明。\n"
        "‘倾听上下文’只用于理解用户长期处境和归纳可复用的支持方式。"
        "不得逐字复述、透露身份或联系方式，不得声称其他学生的经历必然适用于当前用户。\n"
        "回答要先共情，再给2到4个具体可执行步骤，最后说明何时应联系学校心理中心或专业机构。\n\n"
        f"当前问题：{question}\n\n审核资料：\n{knowledge_context}\n\n倾听上下文：\n{conversation_context}"
    )
    return await ai_client.chat([], prompt), knowledge_chunks, personalization
