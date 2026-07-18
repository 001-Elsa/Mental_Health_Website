from collections import Counter

from sqlalchemy.orm import Session

from backend.services.risk_engine import infer_emotion
from database.models import Exercise, UserProfile

STRESSOR_GROUPS = {
    "学习与考试": ("考试", "作业", "论文", "成绩", "复习", "上课"),
    "睡眠": ("失眠", "睡不着", "熬夜", "睡眠"),
    "人际关系": ("室友", "朋友", "同学", "关系", "争吵", "孤独"),
    "家庭": ("父母", "家里", "家庭"),
    "就业与未来": ("实习", "求职", "毕业", "未来", "工作"),
}

COPING_GROUPS = {
    "运动": ("跑步", "散步", "运动", "健身"),
    "表达与倾诉": ("聊天", "倾诉", "说出来", "找朋友"),
    "放松练习": ("呼吸", "冥想", "正念", "放松"),
    "任务拆分": ("计划", "清单", "拆分", "一步一步"),
}

EXERCISE_CATEGORY_BY_EMOTION = {
    "焦虑": ("焦虑缓解", "正念"),
    "低落": ("行为激活", "自我关怀"),
    "烦躁": ("情绪调节", "正念"),
    "平静": ("自我觉察", "成长"),
    "愉悦": ("自我觉察", "成长"),
}


def update_user_profile(db: Session, user_id: int, user_messages: list[str]) -> UserProfile:
    messages = [message.strip() for message in user_messages if message.strip()]
    combined = " ".join(messages[-20:])
    emotions = Counter(infer_emotion(message) for message in messages[-20:])
    dominant = [name for name, _ in emotions.most_common(3)] or ["平静"]
    stressors = [label for label, words in STRESSOR_GROUPS.items() if any(word in combined for word in words)]
    coping = [label for label, words in COPING_GROUPS.items() if any(word in combined for word in words)]
    summary_parts = [f"近期主要情绪为{'、'.join(dominant[:2])}"]
    if stressors:
        summary_parts.append(f"压力来源集中在{'、'.join(stressors[:3])}")
    if coping:
        summary_parts.append(f"更容易接受{'、'.join(coping[:3])}类支持")
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    profile.summary = "；".join(summary_parts) + "。"
    profile.dominant_emotions = "、".join(dominant)
    profile.stressors = "、".join(stressors)
    profile.coping_preferences = "、".join(coping)
    return profile


def recommend_exercises(db: Session, emotion: str, limit: int = 3) -> list[Exercise]:
    categories = EXERCISE_CATEGORY_BY_EMOTION.get(emotion, EXERCISE_CATEGORY_BY_EMOTION["平静"])
    exercises = db.query(Exercise).filter(Exercise.status == "published").all()
    return sorted(
        exercises,
        key=lambda item: (0 if item.category in categories else 1, item.duration_minutes, item.id),
    )[:limit]
