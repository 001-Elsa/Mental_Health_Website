from collections import Counter

from backend.services.risk_engine import infer_emotion


def compress_history(messages: list[dict[str, str]], max_chars: int = 700) -> str:
    """Create a compact, stable memory from older turns without storing chain-of-thought."""
    user_messages = [item["content"].strip() for item in messages if item.get("role") == "user" and item.get("content")]
    if not user_messages:
        return ""
    emotions = Counter(infer_emotion(message) for message in user_messages)
    dominant = "、".join(label for label, _ in emotions.most_common(2))
    key_points = []
    for message in user_messages[-8:]:
        point = message.replace("\n", " ").strip()
        if point and point not in key_points:
            key_points.append(point[:90])
    summary = f"主要情绪：{dominant}。用户近期提到：" + "；".join(key_points)
    return summary[:max_chars]
