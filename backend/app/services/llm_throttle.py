"""
Application-level throttling for outbound LLM calls.

Satisfies cursorrules section 2: every Gemini hit must be spaced by at least
3 seconds so a chatty frontend (or a batched ETL run) can't trip the provider's
RPM circuit breaker (429 Too Many Requests).

The limiter is a global async semaphore-like primitive keyed by provider name.
Concurrency is intentionally serialized (one outbound LLM call at a time per
provider), since this is a low-volume, cost-sensitive workload — not a high
throughput service. If/when we need real RPM-aware throttling, swap the
implementation for a token bucket without touching call sites.
"""

import asyncio
import logging
import os
import time
from typing import Dict

logger = logging.getLogger(__name__)

# Default minimum spacing between Gemini calls (seconds). Overridable via env
# so tests can bypass throttling with LLM_MIN_SPACING_SEC=0.
_DEFAULT_MIN_SPACING_SEC = float(os.getenv("LLM_MIN_SPACING_SEC", "3.0"))


class _MinSpacingLimiter:
    """Serializes calls and enforces a minimum interval between releases."""

    def __init__(self, name: str, min_interval_sec: float) -> None:
        self.name = name
        self._min_interval = max(0.0, min_interval_sec)
        self._last_release_ts: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            if self._min_interval <= 0:
                self._last_release_ts = time.monotonic()
                return

            now = time.monotonic()
            elapsed = now - self._last_release_ts
            wait_for = self._min_interval - elapsed
            if wait_for > 0:
                logger.debug(
                    "llm_throttle name=%s sleeping=%.2fs to enforce min_spacing=%.1fs",
                    self.name, wait_for, self._min_interval,
                )
                await asyncio.sleep(wait_for)
            self._last_release_ts = time.monotonic()


# Per-provider singletons. Add more here when introducing other providers.
_limiters: Dict[str, _MinSpacingLimiter] = {
    "gemini": _MinSpacingLimiter("gemini", _DEFAULT_MIN_SPACING_SEC),
}


async def throttle(provider: str = "gemini") -> None:
    """Block until it is safe to make the next outbound LLM call."""
    limiter = _limiters.get(provider)
    if limiter is None:
        limiter = _MinSpacingLimiter(provider, _DEFAULT_MIN_SPACING_SEC)
        _limiters[provider] = limiter
    await limiter.acquire()
