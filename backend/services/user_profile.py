from collections import Counter

from sqlalchemy.orm import Session

from database.models import Exercise, UserProfile

SEPARATOR = "、"

EMOTION_GROUPS = {
    "焦虑": ("焦虑", "紧张", "担心", "害怕", "压力", "慌", "心烦"),
    "低落": ("难过", "伤心", "哭", "失落", "抑郁", "痛苦", "没劲"),
    "烦躁": ("生气", "愤怒", "烦", "讨厌", "崩溃", "暴躁"),
    "愉悦": ("开心", "高兴", "兴奋", "幸福", "轻松", "顺利"),
}

STRESSOR_GROUPS = {
    "学业": ("考试", "作业", "论文", "成绩", "复习", "上课", "挂科", "绩点"),
    "人际": ("室友", "朋友", "同学", "关系", "争吵", "孤独", "社交", "恋爱"),
    "家庭": ("父母", "家里", "家庭", "亲戚"),
    "睡眠": ("失眠", "睡不着", "熬夜", "睡眠", "早醒", "噩梦"),
    "就业": ("实习", "求职", "毕业", "未来", "工作", "面试", "简历"),
}

COPING_GROUPS = {
    "倾听型": ("聊天", "倾诉", "说出来", "找朋友", "陪我", "听我说"),
    "行动建议型": ("计划", "清单", "拆分", "一步一步", "怎么做", "安排"),
    "放松练习型": ("呼吸", "冥想", "正念", "放松", "散步", "运动"),
    "知识科普型": ("为什么", "原因", "了解", "解释", "资料", "文章"),
}

EXERCISE_CATEGORY_BY_EMOTION = {
    "焦虑": ("焦虑缓解", "压力管理", "正念"),
    "低落": ("情绪调节", "自我关怀", "行为激活"),
    "烦躁": ("情绪调节", "正念", "压力管理"),
    "平稳": ("自我觉察", "成长", "习惯养成"),
    "愉悦": ("自我觉察", "成长", "习惯养成"),
}


def infer_profile_emotion(message: str) -> str:
    for emotion, words in EMOTION_GROUPS.items():
        if any(word in message for word in words):
            return emotion
    return "平稳"


def split_profile_value(value: str) -> list[str]:
    if not value:
        return []
    return [item for item in value.split(SEPARATOR) if item]


def update_user_profile(db: Session, user_id: int, user_messages: list[str]) -> UserProfile:
    messages = [message.strip() for message in user_messages if message.strip()]
    combined = " ".join(messages[-20:])
    emotions = Counter(infer_profile_emotion(message) for message in messages[-20:])
    dominant = [name for name, _ in emotions.most_common(3)] or ["平稳"]
    stressors = [label for label, words in STRESSOR_GROUPS.items() if any(word in combined for word in words)]
    coping = [label for label, words in COPING_GROUPS.items() if any(word in combined for word in words)]

    summary_parts = [f"近期情绪主线以{SEPARATOR.join(dominant[:2])}为主"]
    if stressors:
        summary_parts.append(f"压力来源集中在{SEPARATOR.join(stressors[:3])}")
    if coping:
        summary_parts.append(f"更适合{SEPARATOR.join(coping[:3])}支持")
    if not stressors and not coping:
        summary_parts.append("暂未形成稳定压力来源和支持偏好")

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    profile.summary = "；".join(summary_parts) + "。"
    profile.dominant_emotions = SEPARATOR.join(dominant)
    profile.stressors = SEPARATOR.join(stressors)
    profile.coping_preferences = SEPARATOR.join(coping)
    return profile


def recommend_exercises(db: Session, emotion: str, limit: int = 3) -> list[Exercise]:
    categories = EXERCISE_CATEGORY_BY_EMOTION.get(emotion, EXERCISE_CATEGORY_BY_EMOTION["平稳"])
    exercises = db.query(Exercise).filter(Exercise.status == "published").all()
    return sorted(
        exercises,
        key=lambda item: (0 if item.category in categories else 1, item.duration_minutes, item.id),
    )[:limit]
