from collections import deque
from uuid import UUID, uuid4
from datetime import datetime, timezone
from src.ingestion.contracts import Observation
from src.pipeline.contracts import PipelineEvent

class EventBus:
    """Bounded process-local event journal, consumed by cursor rather than unbounded subscriber queues."""
    def __init__(self, capacity: int = 512):
        if not 1 <= capacity <= 8192:
            raise ValueError("invalid event capacity")
        self._events: deque[PipelineEvent] = deque(maxlen=capacity)
        self._sequence = 0
        self.epoch = uuid4()

    def publish(self, observation: Observation, kind, *, stage=None, state=None):
        self._sequence += 1
        self._events.append(PipelineEvent(
            sequence=self._sequence, event_id=observation.event_id,
            intersection_code=observation.intersection_code, kind=kind,
            stage=stage, state=state, timestamp=datetime.now(timezone.utc)))

    def read(self, after: int, limit: int, epoch: UUID | None = None):
        if after < 0 or not 1 <= limit <= 200:
            raise ValueError("invalid cursor or limit")
        oldest = self._events[0].sequence if self._events else self._sequence + 1
        reset = after > self._sequence or (epoch is not None and epoch != self.epoch)
        gap = reset or after < oldest - 1
        cursor = oldest - 1 if reset else after
        events = [e for e in self._events if e.sequence > cursor][:limit]
        return {"events": events, "gap": gap, "reset": reset, "epoch": self.epoch,
                "next_cursor": events[-1].sequence if events else cursor,
                "oldest_available": oldest, "latest": self._sequence}

    def status(self):
        return {"epoch": str(self.epoch), "capacity": self._events.maxlen, "retained": len(self._events),
                "published": self._sequence,
                "evicted": self._sequence - len(self._events)}
