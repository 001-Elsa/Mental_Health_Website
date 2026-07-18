import json
import time
from typing import Any

from backend.core.config import get_settings


class CacheService:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[str, float]] = {}
        self._redis: Any = None
        redis_url = get_settings().redis_url
        if redis_url:
            try:
                from redis import Redis

                self._redis = Redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def set_code(self, phone: str, code: str, ttl_seconds: int = 300) -> None:
        key = self._key(phone)
        if self._redis:
            self._redis.setex(key, ttl_seconds, code)
            return
        self._memory[key] = (code, time.time() + ttl_seconds)

    def get_code(self, phone: str) -> str | None:
        key = self._key(phone)
        if self._redis:
            value = self._redis.get(key)
            return str(value) if value else None
        item = self._memory.get(key)
        if not item:
            return None
        code, expires_at = item
        if expires_at < time.time():
            self._memory.pop(key, None)
            return None
        return code

    def delete_code(self, phone: str) -> None:
        key = self._key(phone)
        if self._redis:
            self._redis.delete(key)
            return
        self._memory.pop(key, None)

    def get_json(self, key: str) -> Any | None:
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        self.set(key, json.dumps(value, ensure_ascii=False), ttl_seconds)

    def get(self, key: str) -> str | None:
        if self._redis:
            value = self._redis.get(key)
            return str(value) if value is not None else None
        item = self._memory.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at < time.time():
            self._memory.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int = 60) -> None:
        if self._redis:
            self._redis.setex(key, ttl_seconds, value)
            return
        self._memory[key] = (value, time.time() + ttl_seconds)

    def increment(self, key: str, ttl_seconds: int = 60) -> int:
        if self._redis:
            value = int(self._redis.incr(key))
            if value == 1:
                self._redis.expire(key, ttl_seconds)
            return value
        current = self.get(key)
        value = int(current or 0) + 1
        self.set(key, str(value), ttl_seconds)
        return value

    def delete(self, key: str) -> None:
        if self._redis:
            self._redis.delete(key)
            return
        self._memory.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        if self._redis:
            keys = list(self._redis.scan_iter(match=f"{prefix}*", count=200))
            if keys:
                self._redis.delete(*keys)
            return
        for key in [item for item in self._memory if item.startswith(prefix)]:
            self._memory.pop(key, None)

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    @staticmethod
    def _key(phone: str) -> str:
        return f"register_code:{phone}"


cache_service = CacheService()
