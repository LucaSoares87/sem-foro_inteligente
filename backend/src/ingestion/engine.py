import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID

from src.ingestion.contracts import Handoff, Observation, Receipt

def now():
    return datetime.now(timezone.utc)

async def synthetic_handoff(observation: Observation) -> Handoff:
    return Handoff(observation=observation)

class DuplicateConflict(Exception):
    pass

class IngestionUnavailable(Exception):
    pass

class IngestionEngine:
    """Single-event-loop engine with bounded pending work and terminal receipts."""

    def __init__(self, capacity: int = 32, history: int = 128,
                 timeout: float = 1.0, drain_timeout: float = 3.0,
                 processor: Callable[[Observation], Awaitable[Handoff]] = synthetic_handoff):
        if not 1 <= capacity <= 1024 or not 1 <= history <= 4096:
            raise ValueError("invalid storage limits")
        if not 0 < timeout <= 30 or not 0 < drain_timeout <= 60:
            raise ValueError("invalid timeout limits")
        self._queue: asyncio.Queue[UUID] = asyncio.Queue(capacity)
        self._pending: dict[UUID, Receipt] = {}
        self._history: OrderedDict[UUID, Receipt] = OrderedDict()
        self._history_limit = history
        self._timeout = timeout
        self._drain_timeout = drain_timeout
        self._processor = processor
        self._task: asyncio.Task | None = None
        self._accepting = False
        self._closing = False
        self._accepted = self._rejected = self._duplicates = self._conflicts = 0
        self._processed = self._failed = self._cancelled = self._evicted = 0
        self._last_processing_ms: float | None = None
        self._inflight: UUID | None = None

    def start(self):
        if self._task is not None or self._closing:
            raise RuntimeError("engine already started or stopping")
        self._accepting = True
        self._task = asyncio.create_task(self._worker(), name="ingestion-worker")

    @property
    def running(self) -> bool:
        return self._accepting and self._task is not None and not self._task.done()

    def get(self, event_id: UUID) -> Receipt | None:
        return self._pending.get(event_id) or self._history.get(event_id)

    def submit(self, observation: Observation) -> tuple[Receipt, bool]:
        if not self.running:
            self._rejected += 1
            raise IngestionUnavailable
        existing = self.get(observation.event_id)
        if existing is not None:
            if existing.observation != observation:
                self._conflicts += 1
                raise DuplicateConflict
            self._duplicates += 1
            return existing, True
        if self._queue.full():
            self._rejected += 1
            raise IngestionUnavailable
        receipt = Receipt(observation=observation, state="queued", accepted_at=now())
        self._pending[observation.event_id] = receipt
        self._queue.put_nowait(observation.event_id)
        self._accepted += 1
        return receipt, False

    def _finish(self, event_id: UUID, state, *, elapsed=None, code=None):
        receipt = self._pending.pop(event_id)
        terminal = receipt.model_copy(update={
            "state": state, "finished_at": now(),
            "processing_ms": elapsed, "error_code": code,
        })
        self._history[event_id] = terminal
        if len(self._history) > self._history_limit:
            self._history.popitem(last=False)
            self._evicted += 1
        if state == "processed":
            self._processed += 1
            self._last_processing_ms = elapsed
        elif state == "failed":
            self._failed += 1
        else:
            self._cancelled += 1

    async def _worker(self):
        while True:
            event_id = await self._queue.get()
            self._inflight = event_id
            receipt = self._pending[event_id]
            self._pending[event_id] = receipt.model_copy(update={"state": "processing"})
            started = monotonic()
            try:
                async with asyncio.timeout(self._timeout):
                    handoff = await self._processor(receipt.observation)
                if not isinstance(handoff, Handoff) or handoff.observation != receipt.observation:
                    raise ValueError("invalid handoff")
                self._finish(event_id, "processed", elapsed=(monotonic()-started)*1000)
            except asyncio.CancelledError:
                self._finish(event_id, "cancelled", code="shutdown")
                raise
            except TimeoutError:
                self._finish(event_id, "failed", code="processor_timeout")
            except Exception:
                self._finish(event_id, "failed", code="processor_error")
            finally:
                self._inflight = None
                self._queue.task_done()

    async def wait_idle(self):
        await self._queue.join()

    async def stop(self):
        if self._task is None:
            return
        if self._closing:
            raise RuntimeError("concurrent shutdown")
        self._closing = True
        self._accepting = False
        try:
            try:
                await asyncio.wait_for(self._queue.join(), self._drain_timeout)
            except TimeoutError:
                pass
        finally:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            while not self._queue.empty():
                event_id = self._queue.get_nowait()
                self._finish(event_id, "cancelled", code="shutdown")
                self._queue.task_done()
            self._task = None
            self._closing = False

    def status(self):
        return {
            "status": "running" if self.running else "stopping" if self._closing else "stopped",
            "origin": "synthetic",
            "capacity": self._queue.maxsize,
            "queued": self._queue.qsize(),
            "in_flight": int(self._inflight is not None),
            "accepted": self._accepted,
            "rejected": self._rejected,
            "duplicates": self._duplicates,
            "conflicts": self._conflicts,
            "processed": self._processed,
            "failed": self._failed,
            "cancelled": self._cancelled,
            "history_limit": self._history_limit,
            "history_retained": len(self._history),
            "history_evicted": self._evicted,
            "last_processing_ms": self._last_processing_ms,
        }
