import json
import logging
import re
import urllib.request

from backend.core.config import get_settings
from backend.services.risk_engine import RiskAssessment

logger = logging.getLogger(__name__)

CRISIS_REPLY = (
    "我很在意你刚才说的内容。请先确认一件事：你现在是否已经准备实施伤害自己的行为，"
    "或身边有可以用来伤害自己的物品？如果是，请立即离开危险环境，联系身边可信任的人陪着你，"
    "并拨打 120、110 或当地心理援助热线。AI 无法替代紧急救援，但我会继续陪你把下一步说清楚。"
)

SYSTEM_PROMPT = """你是一个真诚、接地气的心理倾听伙伴。你说话的方式像善解人意的朋友，不做诊断、不替代专业医生。

核心原则：
1. 说人话，避免空泛套话。
2. 不复述用户原话，直接回应。
3. 遇到具体问题给具体建议，没有建议就认真陪伴。
4. 如发现自伤自杀风险，严肃建议立即联系专业人士和热线。
"""


class AIClient:
    def _request(self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int) -> str:
        settings = get_settings()
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            settings.deepseek_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.deepseek_api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def review_risk(self, message: str) -> tuple[str, str] | None:
        """Use the model only as a secondary reviewer; rules remain authoritative."""
        if not get_settings().deepseek_api_key:
            return None
        prompt = (
            "你是心理安全分类器。只输出 JSON，不做诊断。"
            "level 只能是 low、medium、high、critical；reason 用一句中文说明可观察到的信号。"
            f"\n用户文本：{message}"
        )
        try:
            raw = self._request(
                [{"role": "system", "content": prompt}],
                temperature=0.0,
                max_tokens=180,
            )
            match = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(match.group(0) if match else raw)
            level = str(data.get("level", "")).lower()
            if level not in {"low", "medium", "high", "critical"}:
                return None
            return level, str(data.get("reason", ""))[:500]
        except Exception as exc:
            logger.warning("Risk model review failed: %s", exc)
            return None

    def chat(
        self,
        history: list[dict[str, str]],
        message: str,
        assessment: RiskAssessment | None = None,
    ) -> str:
        if assessment and assessment.requires_intervention:
            return CRISIS_REPLY

        settings = get_settings()
        if not settings.deepseek_api_key:
            return "AI 服务还没有配置 DEEPSEEK_API_KEY。当前可以先保存对话记录，配置密钥后即可启用真实回复。"

        messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history[-12:],
                {"role": "user", "content": message},
            ]
        try:
            return self._request(messages, temperature=0.7, max_tokens=1600)
        except Exception as exc:
            logger.exception("AI provider request failed: %s", exc)
            return "抱歉，AI 助手暂时无法回应。请稍后再试；如果情况紧急，请优先联系现实中的可信任的人或专业热线。"

ai_client = AIClient()
