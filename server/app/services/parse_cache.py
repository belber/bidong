import time
from threading import Lock

from ..config import settings


class ParseCache:
    """线程安全的 TTL 内存缓存。"""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = float(ttl_seconds)
        self._items: dict = {}
        self._lock = Lock()

    def get(self, key):
        now = time.time()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            return value

    def set(self, key, value) -> None:
        with self._lock:
            self._items[key] = (time.time() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


parse_cache = ParseCache(ttl_seconds=settings.parse_cache_seconds)
