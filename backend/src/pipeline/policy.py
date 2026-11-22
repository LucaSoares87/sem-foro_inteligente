from dataclasses import dataclass
from time import monotonic

class TransientStageError(Exception):
    """Only explicitly classified idempotent work may be retried."""

@dataclass
class CircuitBreaker:
    threshold: int = 3
    cooldown: float = 2.0
    failures: int = 0
    opened_at: float | None = None

    def __post_init__(self):
        if self.threshold < 1 or self.cooldown <= 0:
            raise ValueError("invalid circuit policy")

    def state(self, now=None):
        if self.opened_at is None:
            return "closed"
        if (monotonic() if now is None else now) - self.opened_at >= self.cooldown:
            return "half_open"
        return "open"

    def failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = monotonic()

    def success(self):
        self.failures = 0
        self.opened_at = None
