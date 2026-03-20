"""Retry policy with exponential backoff."""

import time
from dataclasses import dataclass, field


@dataclass
class RetryTracker:
    max_retries: int = 3
    backoff_minutes: list[int] = field(default_factory=lambda: [1, 5, 30])
    _last_attempt: dict[str, float] = field(default_factory=dict)

    def should_retry(self, meeting_id: str, retry_count: int) -> bool:
        return retry_count < self.max_retries

    def get_backoff_seconds(self, retry_count: int) -> int:
        idx = min(retry_count, len(self.backoff_minutes) - 1)
        return self.backoff_minutes[idx] * 60

    def record_attempt(self, meeting_id: str) -> None:
        self._last_attempt[meeting_id] = time.monotonic()

    def is_ready(self, meeting_id: str, retry_count: int) -> bool:
        if meeting_id not in self._last_attempt:
            return True
        elapsed = time.monotonic() - self._last_attempt[meeting_id]
        return elapsed >= self.get_backoff_seconds(retry_count)
