"""Redis 客户端封装，支持开发环境内存回退。"""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any, Dict, Optional

from app.core.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


class _InMemoryRedis:
    def __init__(self) -> None:
        self._data: Dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = threading.Lock()

    def _purge(self, key: Optional[str] = None) -> None:
        now = time.time()
        if key is not None:
            item = self._data.get(key)
            if item and item[1] is not None and item[1] <= now:
                self._data.pop(key, None)
            return
        expired = [k for k, (_, expire_at) in self._data.items() if expire_at is not None and expire_at <= now]
        for k in expired:
            self._data.pop(k, None)

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        with self._lock:
            self._purge(key)
            item = self._data.get(key)
            return None if item is None else item[0]

    def set(self, key: str, value: Any, ex: Optional[int] = None, nx: bool = False):
        with self._lock:
            self._purge(key)
            if nx and key in self._data:
                return False
            expire_at = time.time() + ex if ex else None
            self._data[key] = (value, expire_at)
            return True

    def setex(self, key: str, ttl: int, value: Any):
        return self.set(key, value, ex=ttl)

    def delete(self, *keys: str):
        with self._lock:
            count = 0
            for key in keys:
                if key in self._data:
                    self._data.pop(key, None)
                    count += 1
            return count

    def incr(self, key: str):
        with self._lock:
            self._purge(key)
            current = int(self._data.get(key, (0, None))[0] or 0)
            current += 1
            expire_at = self._data.get(key, (None, None))[1]
            self._data[key] = (current, expire_at)
            return current

    def exists(self, key: str):
        with self._lock:
            self._purge(key)
            return 1 if key in self._data else 0

    def ttl(self, key: str):
        with self._lock:
            self._purge(key)
            item = self._data.get(key)
            if not item:
                return -2
            expire_at = item[1]
            if expire_at is None:
                return -1
            return max(0, int(expire_at - time.time()))


@lru_cache(maxsize=1)
def get_redis_client():
    if redis is not None:
        try:
            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            client.ping()
            return client
        except Exception:
            if not settings.DEBUG:
                raise
    return _InMemoryRedis()

