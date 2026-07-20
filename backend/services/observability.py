from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

AI_REQUESTS = Counter(
    "mental_health_ai_requests_total",
    "AI provider requests by outcome.",
    ("outcome",),
)
AI_DURATION = Histogram(
    "mental_health_ai_response_duration_seconds",
    "Complete AI provider response duration.",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 45, 90),
)
AI_TTFT = Histogram(
    "mental_health_ai_ttft_seconds",
    "Time to first streamed AI token.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20),
)
AI_ACTIVE = Gauge(
    "mental_health_ai_active_requests", "Active AI provider requests.", multiprocess_mode="livesum"
)
AI_RETRIES = Counter("mental_health_ai_retries_total", "AI provider retry attempts.", ("reason",))
