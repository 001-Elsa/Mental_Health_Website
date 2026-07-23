import os
from functools import lru_cache
from pathlib import Path


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_env_file()


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "心理健康AI助手")
        self.environment = os.getenv("APP_ENV", "development")
        self.secret_key = os.getenv("SECRET_KEY", "mental-health-ai-secret-key-change-in-production")
        if self.environment == "production" and self.secret_key in {
            "",
            "change-me-in-production",
            "mental-health-ai-secret-key-change-in-production",
        }:
            raise RuntimeError("Production requires a unique SECRET_KEY")
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
        self.refresh_token_expire_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./mental_health_v2.db")
        self.redis_url = os.getenv("REDIS_URL", "")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_url = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
        self.ai_connect_timeout_seconds = float(os.getenv("AI_CONNECT_TIMEOUT_SECONDS", "5"))
        self.ai_read_timeout_seconds = float(os.getenv("AI_READ_TIMEOUT_SECONDS", "45"))
        self.ai_max_connections = int(os.getenv("AI_MAX_CONNECTIONS", "50"))
        self.ai_max_concurrency = int(os.getenv("AI_MAX_CONCURRENCY", "8"))
        self.ai_max_retries = min(2, max(0, int(os.getenv("AI_MAX_RETRIES", "2"))))
        self.ai_retry_base_seconds = float(os.getenv("AI_RETRY_BASE_SECONDS", "0.25"))
        self.risk_sla_scan_seconds = int(os.getenv("RISK_SLA_SCAN_SECONDS", "30"))
        self.sms_webhook_url = os.getenv("SMS_WEBHOOK_URL", "")
        self.sms_webhook_token = os.getenv("SMS_WEBHOOK_TOKEN", "")
        self.sms_sign_name = os.getenv("SMS_SIGN_NAME", "心灵伙伴")
        self.email_webhook_url = os.getenv("EMAIL_WEBHOOK_URL", "")
        self.email_webhook_token = os.getenv("EMAIL_WEBHOOK_TOKEN", "")
        self.metrics_token = os.getenv("METRICS_TOKEN", "")
        if self.metrics_token == "replace-with-a-separate-random-token":
            self.metrics_token = ""
        self.request_timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
        self.websocket_max_connections = int(os.getenv("WEBSOCKET_MAX_CONNECTIONS", "200"))
        self.websocket_max_connections_per_ip = int(os.getenv("WEBSOCKET_MAX_CONNECTIONS_PER_IP", "5"))
        self.websocket_idle_timeout_seconds = int(os.getenv("WEBSOCKET_IDLE_TIMEOUT_SECONDS", "45"))
        self.cors_origins = [
            item.strip()
            for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if item.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
