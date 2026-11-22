import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID

from src.ingestion.contracts import Handoff, Observation
from src.pipeline.contracts import PipelineReport, StageName, StageResult, StageValue
from src.pipeline.events import EventBus
from src.pipeline.policy import CircuitBreaker, TransientStageError

Adapter = Callable[[Observation, tuple[StageResult, ...]], Awaitable[StageValue]]

async def not_available(observation, previous):
    return StageValue(state="unavailable")

async def synthetic_analytics(observation, previous):
    return StageValue(state="completed", synthetic_vehicle_count=observation.vehicle_count)

async def safe_stage(observation, previous):
    return StageValue(state="completed")

@dataclass(frozen=True)
class StageSpec:
    name: StageName
    adapter: Adapter
    dependencies: tuple[StageName, ...] = ()
    retry_safe: bool = False

class PipelineOrchestrator:
    """Sequential, bounded orchestration; the ingestion engine owns queue and lifecycle."""
    def __init__(self, overrides: Mapping[StageName, Adapter] | None = None,
                 retry_safe: frozenset[StageName] = frozenset(),
                 stage_timeout: float = .08, history: int = 128,
                 event_capacity: int = 512, breaker_threshold: int = 3,
                 breaker_cooldown: float = 2.0):
        if not 0 < stage_timeout <= .09 or not 1 <= history <= 4096:
            raise ValueError("invalid pipeline limits")
        overrides = dict(overrides or {})
        allowed = {"inference", "tracking", "analytics"}
        if not set(overrides) <= allowed or not retry_safe <= set(overrides):
            raise ValueError("invalid stage override or retry policy")
        self._stages = (
            StageSpec("inference", overrides.get("inference", not_available), retry_safe="inference" in retry_safe),
            StageSpec("tracking", overrides.get("tracking", not_available), ("inference",), "tracking" in retry_safe),
            StageSpec("analytics", overrides.get("analytics", synthetic_analytics), retry_safe="analytics" in retry_safe),
            StageSpec("decision", safe_stage),
            StageSpec("reporting", safe_stage),
        )
        self._breakers = {s.name: CircuitBreaker(breaker_threshold, breaker_cooldown) for s in self._stages}
        self._metrics = {s.name: {k: 0 for k in ("completed","unavailable","skipped","failed","circuit_open","retries")}
                         for s in self._stages}
        self._reports: OrderedDict[UUID, PipelineReport] = OrderedDict()
        self._history = history
        self._timeout = stage_timeout
        self._busy = False
        self._completed = self._degraded = self._cancelled = self._evicted = 0
        self.events = EventBus(event_capacity)

    async def _execute(self, spec: StageSpec, observation: Observation, previous: tuple[StageResult,...]):
        start = monotonic()
        breaker = self._breakers[spec.name]
        states = {result.stage: result.state for result in previous}
        def result(state, attempts=0, reason=None, value=None):
            return StageResult(stage=spec.name, state=state, attempts=attempts,
                               elapsed_ms=(monotonic()-start)*1000, reason=reason, value=value)
        if any(states.get(dep) != "completed" for dep in spec.dependencies):
            return result("skipped", reason="dependency_unavailable")
        if breaker.state() == "open":
            return result("circuit_open", reason="circuit_open")
        # A half-open breaker permits a single probe. The orchestrator has one caller.
        attempts = 2 if spec.retry_safe and breaker.state() == "closed" else 1
        for attempt in range(1, attempts+1):
            try:
                async with asyncio.timeout(self._timeout):
                    value = await spec.adapter(observation, previous)
                if not isinstance(value, StageValue):
                    raise ValueError("invalid adapter result")
                if value.synthetic_vehicle_count is not None and (
                    spec.name != "analytics" or value.state != "completed"
                ):
                    raise ValueError("invalid stage value")
                breaker.success()
                return result(value.state, attempt,
                              "not_implemented" if value.state == "unavailable" else None, value)
            except (TransientStageError, TimeoutError) as exc:
                reason = "processor_timeout" if isinstance(exc, TimeoutError) else "transient_exhausted"
                if attempt < attempts:
                    self._metrics[spec.name]["retries"] += 1
                    continue
                breaker.failure()
                return result("failed", attempt, reason)
            except Exception:
                breaker.failure()
                return result("failed", attempt, "processor_error")

    async def process(self, observation: Observation) -> Handoff:
        if self._busy:
            raise RuntimeError("orchestrator must be called by a single ingestion worker")
        self._busy = True
        try:
            self.events.publish(observation, "started")
            results = []
            for spec in self._stages:
                stage = await self._execute(spec, observation, tuple(results))
                results.append(stage)
                self._metrics[spec.name][stage.state] += 1
                self.events.publish(observation, "stage_finished", stage=stage.stage, state=stage.state)
            state = "completed" if all(s.state == "completed" for s in results) else "degraded"
            report = PipelineReport(observation=observation, stages=tuple(results), state=state,
                                    finished_at=datetime.now(timezone.utc))
            self._reports[observation.event_id] = report
            self._reports.move_to_end(observation.event_id)
            if len(self._reports) > self._history:
                self._reports.popitem(last=False)
                self._evicted += 1
            if state == "completed":
                self._completed += 1
            else:
                self._degraded += 1
            self.events.publish(observation, "finished", state=state)
            return Handoff(observation=observation)
        except asyncio.CancelledError:
            self._cancelled += 1
            self.events.publish(observation, "cancelled")
            raise
        finally:
            self._busy = False

    def get(self, event_id: UUID):
        return self._reports.get(event_id)

    def status(self):
        return {"origin":"synthetic", "state":"processing" if self._busy else "idle",
                "inference_mode":"not_loaded", "decision_mode":"abstention_only",
                "completed":self._completed, "degraded":self._degraded,
                "cancelled":self._cancelled, "report_capacity":self._history,
                "reports_retained":len(self._reports), "reports_evicted":self._evicted,
                "event_bus":self.events.status(),
                "stages":{s.name: {**self._metrics[s.name], "circuit":self._breakers[s.name].state()}
                          for s in self._stages}}
