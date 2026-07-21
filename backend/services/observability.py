from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


HTTP_REQUESTS = Counter(
    "mental_health_http_requests_total",
    "HTTP requests by method, normalized route and status.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "mental_health_http_request_duration_seconds",
    "HTTP request duration by normalized route.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 45),
)
HTTP_IN_PROGRESS = Gauge(
    "mental_health_http_requests_in_progress",
    "HTTP requests currently being handled.",
    ("method",),
    multiprocess_mode="livesum",
)

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

CACHE_OPERATIONS = Counter(
    "mental_health_cache_operations_total",
    "Cache operations by result.",
    ("operation", "result"),
)
CACHE_ERRORS = Counter("mental_health_cache_errors_total", "Redis/cache backend failures.", ("operation",))

RISK_CASES = Counter(
    "mental_health_risk_cases_total",
    "Risk cases created, merged, transitioned or escalated.",
    ("operation", "level"),
)
RISK_OPEN = Gauge(
    "mental_health_risk_open_cases", "Open risk cases.", ("level",), multiprocess_mode="max"
)
RISK_SLA_OVERDUE = Gauge(
    "mental_health_risk_sla_overdue_cases", "Risk cases currently past SLA.", multiprocess_mode="max"
)
