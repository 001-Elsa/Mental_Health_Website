from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import AsyncIterator

import httpx

from backend.core.config import get_settings
from backend.services.observability import (
    AI_ACTIVE,
    AI_DURATION,
    AI_REQUESTS,
    AI_RETRIES,
    AI_TTFT,
)
from backend.services.risk_engine import RiskAssessment

logger = logging.getLogger(__name__)

CRISIS_REPLY = (
    "我很在意你刚才说的内容。请先确认一件事：你现在是否已经准备实施伤害自己的行为，"
    "或身边有可以用来伤害自己的物品？如果是，请立即离开危险环境，联系身边可信任的人陪着你，"
    "并拨打 120、110 或当地心理援助热线。AI 无法替代紧急救援，但我会继续陪你把下一步说清楚。"
)
FALLBACK_REPLY = (
    "抱歉，AI 助手暂时无法响应。请稍后再试；如果情况紧急，请优先联系现实中可信任的人、"
    "学校心理中心或拨打 120 / 110。"
)
UNCONFIGURED_REPLY = "AI 服务尚未配置 DEEPSEEK_API_KEY；当前会保存对话，配置密钥后即可启用真实回复。"

SYSTEM_PROMPT = """你是一位真诚、接地气的心理倾听伙伴。你不作诊断，也不替代专业医生。
使用清楚、具体、尊重的语言；不复述用户原话；发现自伤或自杀风险时，明确建议立即联系现实支持和紧急热线。"""


class AIProviderError(RuntimeError):
    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class AIClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(settings.ai_max_concurrency)
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        settings = get_settings()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.ai_connect_timeout_seconds,
                read=settings.ai_read_timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=settings.ai_max_connections,
                max_keepalive_connections=max(5, settings.ai_max_connections // 2),
            ),
            headers={"Content-Type": "application/json"},
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ) -> dict:
        return {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    async def _post(self, payload: dict) -> httpx.Response:
        await self.start()
        settings = get_settings()
        assert self._client is not None
        response = await self._client.post(
            settings.deepseek_url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        )
        if response.status_code == 429:
            raise AIProviderError("rate_limited", retryable=True)
        if response.status_code in {408, 425} or response.status_code >= 500:
            raise AIProviderError(f"http_{response.status_code}", retryable=True)
        if response.status_code in {401, 403}:
            raise AIProviderError("invalid_api_key")
        if response.is_error:
            raise AIProviderError(f"http_{response.status_code}")
        return response

    async def _request(self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int) -> str:
        settings = get_settings()
        started = time.perf_counter()
        async with self._semaphore:
            AI_ACTIVE.inc()
            try:
                for attempt in range(settings.ai_max_retries + 1):
                    try:
                        response = await self._post(self._payload(messages, temperature=temperature, max_tokens=max_tokens))
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        if not isinstance(content, str) or not content.strip():
                            raise AIProviderError("invalid_response")
                        AI_REQUESTS.labels("success").inc()
                        return content
                    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                        error = AIProviderError("connect_timeout", retryable=True)
                        error.__cause__ = exc
                    except httpx.ReadTimeout as exc:
                        error = AIProviderError("read_timeout", retryable=True)
                        error.__cause__ = exc
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        error = AIProviderError("invalid_response")
                        error.__cause__ = exc
                    except AIProviderError as exc:
                        error = exc
                    if not error.retryable or attempt >= settings.ai_max_retries:
                        AI_REQUESTS.labels(error.reason).inc()
                        raise error
                    AI_RETRIES.labels(error.reason).inc()
                    delay = settings.ai_retry_base_seconds * (2**attempt) + random.uniform(0, 0.1)
                    await asyncio.sleep(delay)
                raise AIProviderError("unknown")
            finally:
                AI_ACTIVE.dec()
                AI_DURATION.observe(time.perf_counter() - started)

    async def review_risk(self, message: str) -> tuple[str, str] | None:
        if not get_settings().deepseek_api_key:
            return None
        prompt = (
            "你是心理安全分类器。只输出 JSON，不作诊断。level 只能是 low、medium、high、critical；"
            f"reason 用一句中文说明可观察信号。\n用户文本：{message}"
        )
        try:
            raw = await self._request([{"role": "system", "content": prompt}], temperature=0.0, max_tokens=180)
            match = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(match.group(0) if match else raw)
            level = str(data.get("level", "")).lower()
            if level not in {"low", "medium", "high", "critical"}:
                return None
            return level, str(data.get("reason", ""))[:500]
        except Exception as exc:
            logger.warning("Risk model review failed: %s", exc)
            return None

    async def chat(
        self,
        history: list[dict[str, str]],
        message: str,
        assessment: RiskAssessment | None = None,
    ) -> str:
        if assessment and assessment.requires_intervention:
            return CRISIS_REPLY
        if not get_settings().deepseek_api_key:
            return UNCONFIGURED_REPLY
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history[-12:], {"role": "user", "content": message}]
        try:
            return await self._request(messages, temperature=0.7, max_tokens=1600)
        except Exception as exc:
            logger.warning("AI provider request degraded safely: %s", exc)
            AI_REQUESTS.labels("fallback").inc()
            return FALLBACK_REPLY

    async def stream_chat(
        self,
        history: list[dict[str, str]],
        message: str,
        assessment: RiskAssessment | None = None,
    ) -> AsyncIterator[str]:
        if assessment and assessment.requires_intervention:
            yield CRISIS_REPLY
            return
        settings = get_settings()
        if not settings.deepseek_api_key:
            yield UNCONFIGURED_REPLY
            return

        await self.start()
        assert self._client is not None
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history[-12:], {"role": "user", "content": message}]
        started = time.perf_counter()
        first_token = True
        async with self._semaphore:
            AI_ACTIVE.inc()
            try:
                async with self._client.stream(
                    "POST",
                    settings.deepseek_url,
                    json=self._payload(messages, temperature=0.7, max_tokens=1600, stream=True),
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                ) as response:
                    if response.status_code != 200:
                        AI_REQUESTS.labels(f"http_{response.status_code}").inc()
                        yield FALLBACK_REPLY
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)["choices"][0]["delta"].get("content", "")
                        except (KeyError, TypeError, json.JSONDecodeError):
                            continue
                        if chunk:
                            if first_token:
                                AI_TTFT.observe(time.perf_counter() - started)
                                first_token = False
                            yield chunk
                    AI_REQUESTS.labels("success").inc()
            except (httpx.HTTPError, asyncio.CancelledError) as exc:
                AI_REQUESTS.labels("stream_error").inc()
                if isinstance(exc, asyncio.CancelledError):
                    raise
                logger.warning("Streaming AI request failed: %s", exc)
                yield FALLBACK_REPLY
            finally:
                AI_ACTIVE.dec()
                AI_DURATION.observe(time.perf_counter() - started)


ai_client = AIClient()
