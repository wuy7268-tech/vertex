import json
import threading
import time
from typing import Any, Protocol

import redis


class Cache(Protocol):
    kind: str

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    def get_int(self, key: str) -> int: ...
    def incr(self, key: str) -> int: ...
    def set_nx(self, key: str, value: str, ttl: int) -> bool: ...
    def get_str(self, key: str) -> str | None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


class MemoryCache:
    kind = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[Any, float | None]] = {}

    def _purge(self, key: str) -> None:
        item = self._data.get(key)
        if item is None:
            return
        _, exp = item
        if exp is not None and exp <= time.time():
            self._data.pop(key, None)

    def get(self, key: str) -> Any | None:
        with self._lock:
            self._purge(key)
            item = self._data.get(key)
            return None if item is None else item[0]

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            exp = time.time() + ttl if ttl else None
            self._data[key] = (value, exp)

    def get_int(self, key: str) -> int:
        value = self.get(key)
        return int(value or 0)

    def incr(self, key: str) -> int:
        with self._lock:
            self._purge(key)
            current = self._data.get(key)
            n = int(current[0] if current else 0) + 1
            self._data[key] = (n, None)
            return n

    def set_nx(self, key: str, value: str, ttl: int) -> bool:
        with self._lock:
            self._purge(key)
            if key in self._data:
                return False
            self._data[key] = (value, time.time() + ttl)
            return True

    def get_str(self, key: str) -> str | None:
        value = self.get(key)
        return None if value is None else str(value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class RedisCache:
    kind = "redis"

    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    def get(self, key: str) -> Any | None:
        raw = self._r.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl: int) -> None:
        payload = json.dumps(value)
        if ttl:
            self._r.set(key, payload, ex=ttl)
        else:
            self._r.set(key, payload)

    def get_int(self, key: str) -> int:
        raw = self._r.get(f"int:{key}")
        return int(raw) if raw else 0

    def incr(self, key: str) -> int:
        return int(self._r.incr(f"int:{key}"))

    def set_nx(self, key: str, value: str, ttl: int) -> bool:
        return bool(self._r.set(key, value, nx=True, ex=ttl))

    def get_str(self, key: str) -> str | None:
        raw = self._r.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode()
        return str(raw)

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def clear(self) -> None:
        self._r.flushdb()


def make_cache(url: str) -> Cache:
    if not url:
        return MemoryCache()
    try:
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
        client.ping()
        return RedisCache(client)
    except redis.RedisError:
        return MemoryCache()
