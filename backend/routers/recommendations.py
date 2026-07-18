from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.services.user_profile import recommend_exercises
from database.database import get_sync_db
from database.models import Article, Consultation, MoodLog, User, UserProfile

router = APIRouter(prefix="/api/recommendations", tags=["内容推荐"])

EMOTION_CATEGORIES = {
    "焦虑": ("焦虑缓解", "压力管理", "睡眠"),
    "低落": ("情绪调节", "自我关怀", "人际支持"),
    "烦躁": ("情绪调节", "正念", "压力管理"),
    "平静": ("心理科普", "成长", "人际关系"),
    "愉悦": ("成长", "习惯养成", "人际关系"),
}

RecommendationEmotion = Literal["焦虑", "低落", "烦躁", "平静", "愉悦"]


class RecommendationPreferenceReq(BaseModel):
    emotion: RecommendationEmotion


def _inferred_emotion(recent_consult: Consultation | None, recent_mood: MoodLog | None, profile: UserProfile | None) -> str:
    emotion = recent_consult.emotion_tag if recent_consult else ""
    if not emotion and recent_mood and recent_mood.score <= 4:
        emotion = "低落"
    return emotion or (profile.dominant_emotions.split("、")[0] if profile and profile.dominant_emotions else "平静")


def _effective_emotion(recent_consult: Consultation | None, recent_mood: MoodLog | None, profile: UserProfile | None) -> tuple[str, bool]:
    manual_emotion = profile.recommendation_emotion if profile and profile.recommendation_emotion in EMOTION_CATEGORIES else ""
    return (manual_emotion, True) if manual_emotion else (_inferred_emotion(recent_consult, recent_mood, profile), False)


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
    recent_mood = db.query(MoodLog).filter(
        MoodLog.user_id == current_user.id
    ).order_by(MoodLog.created_at.desc()).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    emotion, is_manual = _effective_emotion(recent_consult, recent_mood, profile)
    preferred = EMOTION_CATEGORIES.get(emotion, EMOTION_CATEGORIES["平静"])

    articles = db.query(Article).filter(Article.status == "已发布").all()
    ranked = sorted(
        articles,
        key=lambda article: (
            0 if any(category in article.category for category in preferred) else 1,
            -(article.read_count or 0),
        ),
    )[:6]
    return {
        "profile": {
            "emotion": emotion,
            "is_manual": is_manual,
            "recent_mood": recent_mood.score if recent_mood else None,
            "summary": profile.summary if profile else "",
            "stressors": profile.stressors.split("、") if profile and profile.stressors else [],
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
                    "read_count": article.read_count,
                    "created_at": article.created_at,
                },
                "reason": f"根据你选择的{emotion}状态推荐" if is_manual and any(category in article.category for category in preferred) else f"根据当前{emotion}状态推荐" if any(category in article.category for category in preferred) else "同学们近期常读",
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
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    emotion, is_manual = _effective_emotion(recent_consult, None, profile)
    rows = recommend_exercises(db, emotion)
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
                "reason": f"根据你选择的{emotion}状态推荐" if is_manual else f"根据当前{emotion}状态推荐",
            }
            for row in rows
        ],
    }
