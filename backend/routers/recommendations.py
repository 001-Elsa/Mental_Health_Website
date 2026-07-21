from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.services.user_profile import recommend_exercises, split_profile_value
from database.database import get_sync_db
from database.models import Article, Consultation, MoodLog, User, UserProfile

router = APIRouter(prefix="/api/recommendations", tags=["内容推荐"])

PUBLISHED_STATUSES = {"已发布", "宸插彂甯?"}

EMOTION_CATEGORIES = {
    "焦虑": ("焦虑缓解", "压力管理", "睡眠", "正念"),
    "低落": ("情绪调节", "自我关怀", "人际支持", "行为激活"),
    "烦躁": ("情绪调节", "正念", "压力管理"),
    "平稳": ("心理科普", "成长", "人际关系", "习惯养成"),
    "愉悦": ("成长", "习惯养成", "人际关系"),
}

STRESSOR_CATEGORIES = {
    "学业": ("考试", "学习", "压力管理", "焦虑缓解"),
    "人际": ("人际关系", "沟通", "人际支持"),
    "家庭": ("家庭", "关系", "自我关怀"),
    "睡眠": ("睡眠", "放松", "正念"),
    "就业": ("就业", "未来", "成长", "压力管理"),
}

RecommendationEmotion = Literal["焦虑", "低落", "烦躁", "平稳", "愉悦"]


class RecommendationPreferenceReq(BaseModel):
    emotion: RecommendationEmotion


def _recent_mood_signal(db: Session, user_id: int) -> tuple[MoodLog | None, str]:
    rows = (
        db.query(MoodLog)
        .filter(MoodLog.user_id == user_id)
        .order_by(MoodLog.created_at.desc(), MoodLog.id.desc())
        .limit(7)
        .all()
    )
    if not rows:
        return None, ""
    scores = [float(row.score) for row in reversed(rows)]
    if len(scores) >= 3 and scores[-1] <= scores[0] - 2:
        return rows[0], "最近情绪评分有下降趋势"
    if scores[-1] <= 4:
        return rows[0], "最近一次情绪评分偏低"
    return rows[0], ""


def _inferred_emotion(recent_consult: Consultation | None, recent_mood: MoodLog | None, profile: UserProfile | None) -> str:
    if recent_consult and recent_consult.emotion_tag in EMOTION_CATEGORIES:
        return recent_consult.emotion_tag
    if recent_mood and recent_mood.score <= 4:
        return "低落"
    dominant = split_profile_value(profile.dominant_emotions if profile else "")
    return dominant[0] if dominant and dominant[0] in EMOTION_CATEGORIES else "平稳"


def _effective_emotion(recent_consult: Consultation | None, recent_mood: MoodLog | None, profile: UserProfile | None) -> tuple[str, bool]:
    manual_emotion = profile.recommendation_emotion if profile and profile.recommendation_emotion in EMOTION_CATEGORIES else ""
    return (manual_emotion, True) if manual_emotion else (_inferred_emotion(recent_consult, recent_mood, profile), False)


def _article_matches(article: Article, categories: tuple[str, ...]) -> bool:
    text = f"{article.category} {article.title} {article.summary}"
    return any(category in text for category in categories)


def _reason(
    *,
    article: Article,
    emotion: str,
    is_manual: bool,
    profile: UserProfile | None,
    mood_signal: str,
) -> str:
    stressors = split_profile_value(profile.stressors if profile else "")
    preferences = split_profile_value(profile.coping_preferences if profile else "")
    parts = []
    if is_manual:
        parts.append(f"你当前手动选择了{emotion}状态")
    else:
        parts.append(f"系统根据近期对话和记录识别到{emotion}主线")
    if mood_signal:
        parts.append(mood_signal)
    matched_stressor = next((stressor for stressor in stressors if _article_matches(article, STRESSOR_CATEGORIES.get(stressor, ()))), "")
    if matched_stressor:
        parts.append(f"内容与{matched_stressor}压力来源相关")
    if preferences:
        parts.append(f"更贴近你的{preferences[0]}支持偏好")
    return "，".join(parts) + "。"


@router.put("/preference")
def save_recommendation_preference(
    payload: RecommendationPreferenceReq,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if profile is None:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
    profile.recommendation_emotion = payload.emotion
    db.commit()
    return {"emotion": payload.emotion, "is_manual": True}


@router.get("/articles")
def recommend_articles(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    recent_consult = db.query(Consultation).filter(
        Consultation.user_id == current_user.id
    ).order_by(Consultation.created_at.desc()).first()
    recent_mood, mood_signal = _recent_mood_signal(db, current_user.id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    emotion, is_manual = _effective_emotion(recent_consult, recent_mood, profile)
    preferred = EMOTION_CATEGORIES.get(emotion, EMOTION_CATEGORIES["平稳"])
    stressors = split_profile_value(profile.stressors if profile else "")
    stressor_categories = tuple(category for stressor in stressors for category in STRESSOR_CATEGORIES.get(stressor, ()))

    articles = db.query(Article).filter(Article.status.in_(PUBLISHED_STATUSES)).all()
    ranked = sorted(
        articles,
        key=lambda article: (
            0 if _article_matches(article, preferred) else 1,
            0 if stressor_categories and _article_matches(article, stressor_categories) else 1,
            -(article.read_count or 0),
        ),
    )[:6]
    return {
        "profile": {
            "emotion": emotion,
            "is_manual": is_manual,
            "recent_mood": recent_mood.score if recent_mood else None,
            "mood_signal": mood_signal,
            "summary": profile.summary if profile else "",
            "stressors": stressors,
            "coping_preferences": split_profile_value(profile.coping_preferences if profile else ""),
            "dominant_emotions": split_profile_value(profile.dominant_emotions if profile else ""),
        },
        "items": [
            {
                "article": {
                    "id": article.id,
                    "title": article.title,
                    "author": article.author,
                    "summary": article.summary,
                    "cover_image": article.cover_image,
                    "content": article.content,
                    "category": article.category,
                    "status": article.status,
                    "source_name": article.source_name,
                    "source_url": article.source_url,
                    "published_at": article.published_at,
                    "read_count": article.read_count,
                    "created_at": article.created_at,
                },
                "reason": _reason(
                    article=article,
                    emotion=emotion,
                    is_manual=is_manual,
                    profile=profile,
                    mood_signal=mood_signal,
                ),
            }
            for article in ranked
        ],
    }


@router.get("/exercises")
def recommend_support_exercises(
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    recent_consult = db.query(Consultation).filter(
        Consultation.user_id == current_user.id
    ).order_by(Consultation.created_at.desc()).first()
    recent_mood, mood_signal = _recent_mood_signal(db, current_user.id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    emotion, is_manual = _effective_emotion(recent_consult, recent_mood, profile)
    rows = recommend_exercises(db, emotion)
    preference = split_profile_value(profile.coping_preferences if profile else "")
    return {
        "emotion": emotion,
        "is_manual": is_manual,
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "category": row.category,
                "description": row.description,
                "steps": row.steps,
                "duration_minutes": row.duration_minutes,
                "reason": "，".join(
                    item for item in [
                        f"基于{emotion}状态推荐",
                        mood_signal,
                        f"贴近你的{preference[0]}偏好" if preference else "",
                    ] if item
                ) + "。",
            }
            for row in rows
        ],
    }
