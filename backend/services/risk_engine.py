from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    score: int
    signals: tuple[str, ...]

    @property
    def reason(self) -> str:
        return "、".join(self.signals)

    @property
    def requires_intervention(self) -> bool:
        return self.level in {"high", "critical"}


CRITICAL_PATTERNS = {
    "明确自杀意图": ("自杀", "轻生", "结束生命", "不想活了", "活不下去"),
    "具体自伤方式": ("割腕", "跳楼", "上吊", "吃安眠药", "伤害自己"),
    "近期行动计划": ("今晚就", "马上去死", "已经准备", "遗书", "告别"),
}

DISTRESS_PATTERNS = {
    "强烈绝望感": ("没有希望", "没人会在乎", "一切都没意义", "撑不下去"),
    "持续低落": ("抑郁", "很痛苦", "崩溃", "每天都难受"),
    "社会隔离": ("不想见人", "没有人能帮我", "只有我一个人"),
    "睡眠或功能受损": ("整夜睡不着", "无法上课", "什么都做不了"),
}

PROTECTIVE_PATTERNS = ("不会伤害自己", "没有自杀想法", "只是难过", "有人陪我")


def assess_risk(message: str, recent_mood_scores: list[float] | None = None) -> RiskAssessment:
    text = message.strip().lower()
    protective_matches = [pattern for pattern in PROTECTIVE_PATTERNS if pattern in text]
    signal_text = text
    for pattern in protective_matches:
        signal_text = signal_text.replace(pattern, "")
    score = 0
    signals: list[str] = []

    for label, patterns in CRITICAL_PATTERNS.items():
        if any(pattern in signal_text for pattern in patterns):
            score += 45 if label in {"近期行动计划", "明确自杀意图"} else 35
            signals.append(label)

    for label, patterns in DISTRESS_PATTERNS.items():
        if any(pattern in signal_text for pattern in patterns):
            score += 15
            signals.append(label)

    mood_scores = recent_mood_scores or []
    if len(mood_scores) >= 3 and mood_scores[-1] <= 3:
        decline = mood_scores[0] - mood_scores[-1]
        if decline >= 2:
            score += 20
            signals.append("近期情绪连续下降")
    elif mood_scores and mood_scores[-1] <= 2:
        score += 10
        signals.append("近期情绪评分很低")

    if protective_matches:
        score = max(0, score - 20)
        signals.append("包含保护性表达")

    score = min(score, 100)
    if score >= 75:
        level = "critical"
    elif score >= 45:
        level = "high"
    elif score >= 20:
        level = "medium"
    else:
        level = "low"

    return RiskAssessment(level=level, score=score, signals=tuple(signals))


def infer_emotion(message: str) -> str:
    groups = (
        ("焦虑", ("焦虑", "紧张", "担心", "害怕", "压力")),
        ("低落", ("难过", "伤心", "哭", "失落", "抑郁", "痛苦")),
        ("烦躁", ("生气", "愤怒", "烦", "讨厌", "崩溃")),
        ("愉悦", ("开心", "高兴", "兴奋", "幸福", "轻松")),
    )
    for emotion, words in groups:
        if any(word in message for word in words):
            return emotion
    return "平静"
