from __future__ import annotations

import json
import random
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from backend.core.config import get_settings
from backend.services.observability import CACHE_ERRORS, CACHE_OPERATIONS

NULL_SENTINEL = "__MENTAL_HEALTH_CACHE_NULL__"


class CacheService:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[str, float]] = {}
        self._local_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._redis: Any = None
        self._redis_disabled_until = 0.0
        redis_url = get_settings().redis_url
        if redis_url:
            try:
                from redis import Redis

                self._redis = Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.25,
                    socket_timeout=0.25,
                    health_check_interval=30,
                )
                self._redis.ping()
            except Exception:
                self._redis = None

    def _redis_call(self, operation: str, callback: Callable[[], Any]) -> tuple[bool, Any]:
        if not self._redis or time.monotonic() < self._redis_disabled_until:
            if self._redis:
                CACHE_OPERATIONS.labels(operation, "circuit_open").inc()
            return False, None
        try:
            value = callback()
            self._redis_disabled_until = 0.0
            return True, value
        except Exception:
            CACHE_ERRORS.labels(operation).inc()
            self._redis_disabled_until = time.monotonic() + 5.0
            return False, None

    def set_code(self, phone: str, code: str, ttl_seconds: int = 300) -> None:
        key = self._key(phone)
        ok, _ = self._redis_call("set_code", lambda: self._redis.setex(key, ttl_seconds, code))
        if not ok:
            self._memory[key] = (code, time.time() + ttl_seconds)

    def get_code(self, phone: str) -> str | None:
        return self.get(self._key(phone))

    def delete_code(self, phone: str) -> None:
        self.delete(self._key(phone))

    def get_json(self, key: str) -> Any | None:
        raw = self.get(key)
        if raw is None or raw == NULL_SENTINEL:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            self.delete(key)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 60, *, jitter_seconds: int = 0) -> None:
        ttl = ttl_seconds + (random.randint(0, jitter_seconds) if jitter_seconds > 0 else 0)
        self.set(key, json.dumps(value, ensure_ascii=False), ttl)

    def get(self, key: str) -> str | None:
        ok, value = self._redis_call("get", lambda: self._redis.get(key))
        if ok:
            CACHE_OPERATIONS.labels("get", "hit" if value is not None else "miss").inc()
            return str(value) if value is not None else None
        item = self._memory.get(key)
        if not item:
            CACHE_OPERATIONS.labels("get", "miss").inc()
            return None
        value, expires_at = item
        if expires_at < time.time():
            self._memory.pop(key, None)
            CACHE_OPERATIONS.labels("get", "expired").inc()
            return None
        CACHE_OPERATIONS.labels("get", "hit").inc()
        return value

    def set(self, key: str, value: str, ttl_seconds: int = 60) -> None:
        ok, _ = self._redis_call("set", lambda: self._redis.setex(key, ttl_seconds, value))
        if ok:
            CACHE_OPERATIONS.labels("set", "ok").inc()
            return
        self._memory[key] = (value, time.time() + ttl_seconds)

    def increment(self, key: str, ttl_seconds: int = 60) -> int:
        def increment_redis() -> int:
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.ttl(key)
            value, ttl = pipeline.execute()
            if ttl < 0:
                self._redis.expire(key, ttl_seconds)
            return int(value)

        ok, value = self._redis_call("increment", increment_redis)
        if ok:
            return int(value)
        current = self.get(key)
        value = int(current or 0) + 1
        self.set(key, str(value), ttl_seconds)
        return value

    def delete(self, key: str) -> None:
        ok, _ = self._redis_call("delete", lambda: self._redis.delete(key))
        if not ok:
            self._memory.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        def delete_matching() -> None:
            keys = list(self._redis.scan_iter(match=f"{prefix}*", count=200))
            if keys:
                self._redis.delete(*keys)

        ok, _ = self._redis_call("delete_prefix", delete_matching)
        if not ok:
            for key in [item for item in self._memory if item.startswith(prefix)]:
                self._memory.pop(key, None)

    def get_or_load_json(
        self,
        key: str,
        loader: Callable[[], Any | None],
        *,
        ttl_seconds: int,
        negative_ttl_seconds: int = 20,
        jitter_seconds: int = 30,
    ) -> Any | None:
        """Cache-aside with negative caching, randomized TTL and single-flight fill."""
        raw = self.get(key)
        if raw is not None:
            if raw == NULL_SENTINEL:
                CACHE_OPERATIONS.labels("load", "negative_hit").inc()
                return None
            try:
                return json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                self.delete(key)

        with self._locks_guard:
            local_lock = self._local_locks.setdefault(key, threading.Lock())
        with local_lock:
            raw = self.get(key)
            if raw is not None:
                return None if raw == NULL_SENTINEL else json.loads(raw)
            token = uuid.uuid4().hex
            lock_key = f"lock:cache-fill:{key}"
            ok, owns_redis_lock = self._redis_call(
                "lock", lambda: bool(self._redis.set(lock_key, token, nx=True, ex=10))
            )
            if ok and not owns_redis_lock:
                for _ in range(20):
                    time.sleep(0.025)
                    raw = self.get(key)
                    if raw is not None:
                        return None if raw == NULL_SENTINEL else json.loads(raw)
            try:
                value = loader()
                if value is None:
                    self.set(key, NULL_SENTINEL, negative_ttl_seconds + random.randint(0, 5))
                    CACHE_OPERATIONS.labels("load", "negative_fill").inc()
                    return None
                self.set_json(key, value, ttl_seconds, jitter_seconds=jitter_seconds)
                CACHE_OPERATIONS.labels("load", "fill").inc()
                return value
            finally:
                if owns_redis_lock:
                    script = (
                        "if redis.call('get', KEYS[1]) == ARGV[1] then "
                        "return redis.call('del', KEYS[1]) else return 0 end"
                    )
                    self._redis_call("unlock", lambda: self._redis.eval(script, 1, lock_key, token))

    @property
    def backend(self) -> str:
        if self._redis and time.monotonic() < self._redis_disabled_until:
            return "redis_degraded"
        return "redis" if self._redis else "memory"

    @staticmethod
    def _key(phone: str) -> str:
        return f"verification:sms:{phone}"


cache_service = CacheService()
