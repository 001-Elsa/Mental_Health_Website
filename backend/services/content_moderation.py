from dataclasses import dataclass

from sqlalchemy.orm import Session

from database.models import SensitiveWord


DEFAULT_SENSITIVE_WORDS = ("联系方式", "加微信", "代考", "辱骂", "人肉")


@dataclass(frozen=True)
class ModerationResult:
    status: str
    reason: str = ""
    matched_words: tuple[str, ...] = ()


def moderate_content(db: Session, *parts: str) -> ModerationResult:
    text = " ".join(parts).lower()
    configured = [
        row.word
        for row in db.query(SensitiveWord).filter(SensitiveWord.enabled.is_(True)).all()
    ]
    vocabulary = tuple(dict.fromkeys((*DEFAULT_SENSITIVE_WORDS, *configured)))
    matched = tuple(word for word in vocabulary if word.lower() in text)
    if matched:
        return ModerationResult(
            status="pending_review",
            reason=f"命中社区安全词：{'、'.join(matched)}",
            matched_words=matched,
        )
    return ModerationResult(status="published")
