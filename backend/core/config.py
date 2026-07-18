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
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 30)))
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./mental_health_v2.db")
        self.redis_url = os.getenv("REDIS_URL", "")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_url = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
        self.sms_webhook_url = os.getenv("SMS_WEBHOOK_URL", "")
        self.sms_webhook_token = os.getenv("SMS_WEBHOOK_TOKEN", "")
        self.sms_sign_name = os.getenv("SMS_SIGN_NAME", "心灵伙伴")
        self.email_webhook_url = os.getenv("EMAIL_WEBHOOK_URL", "")
        self.email_webhook_token = os.getenv("EMAIL_WEBHOOK_TOKEN", "")
        self.cors_origins = [
            item.strip()
            for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if item.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
