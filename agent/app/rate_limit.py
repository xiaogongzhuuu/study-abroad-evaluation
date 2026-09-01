import math
import threading
import time
from collections import defaultdict, deque


class FixedWindowRateLimiter:
    """单进程内的轻量限流器，适合本项目当前的单实例部署。"""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._next_cleanup = 0.0

    def check(
        self,
        scope: str,
        client: str,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> int | None:
        """允许时返回 None；超限时返回至少 1 秒的 Retry-After。"""
        if limit <= 0:
            return None
        current = time.monotonic() if now is None else now
        cutoff = current - window_seconds
        with self._lock:
            # 定期移除不再活跃的来源，避免长期运行时字典无限增长。
            if current >= self._next_cleanup or len(self._events) >= 10_000:
                for stale_key, stale_events in list(self._events.items()):
                    while stale_events and stale_events[0] <= cutoff:
                        stale_events.popleft()
                    if not stale_events:
                        del self._events[stale_key]
                self._next_cleanup = current + window_seconds

            key = (scope, client)
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, math.ceil(events[0] + window_seconds - current))
            events.append(current)
            return None

    def clear(self) -> None:
        """仅供测试隔离使用。"""
        with self._lock:
            self._events.clear()
            self._next_cleanup = 0.0


rate_limiter = FixedWindowRateLimiter()
