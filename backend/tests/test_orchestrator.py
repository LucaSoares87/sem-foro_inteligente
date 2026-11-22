import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ingestion.contracts import Observation
from src.ingestion.engine import IngestionEngine
from src.pipeline.contracts import PipelineReport, StageValue
from src.pipeline.events import EventBus
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.policy import CircuitBreaker, TransientStageError

def observation(n=1, intersection="CR_01"):
    return Observation(event_id=uuid4(), intersection_code=intersection,
                       source_id="CAM_01", sequence=n,
                       captured_at=datetime.now(timezone.utc), vehicle_count=n)

async def ok(o, previous):
    return StageValue(state="completed")

def test_default_pipeline_and_existing_ingestion():
    async def run():
        pipeline = PipelineOrchestrator()
        engine = IngestionEngine(processor=pipeline.process)
        engine.start()
        try:
            one, two = observation(3), observation(4, "CR_02")
            engine.submit(one)
            engine.submit(two)
            assert engine.submit(one)[1] is True
            await engine.wait_idle()
            assert engine.get(one.event_id).state == "processed"
            assert engine.get(two.event_id).state == "processed"
            report = pipeline.get(one.event_id)
            assert report.observation == one
            assert report.state == "degraded"
            assert report.decision == "abstain"
            assert [(s.stage,s.state) for s in report.stages] == [
                ("inference","unavailable"), ("tracking","skipped"),
                ("analytics","completed"), ("decision","completed"), ("reporting","completed")]
            assert report.stages[2].value.synthetic_vehicle_count == 3
            assert pipeline.get(two.event_id).observation == two
            journal = pipeline.events.read(0, 100)
            assert len(journal["events"]) == 14
            assert journal["events"][0].event_id == one.event_id
            assert journal["events"][-1].event_id == two.event_id
            assert not journal["gap"]
            assert pipeline.status()["degraded"] == 2
            assert pipeline.status()["state"] == "idle"
            with pytest.raises(ValidationError):
                PipelineReport.model_validate({**report.model_dump(), "decision":"green"})
        finally:
            await engine.stop()
    asyncio.run(run())

def test_all_adapters_completed_still_abstain_and_history_bounded():
    async def run():
        pipeline = PipelineOrchestrator(overrides={"inference":ok,"tracking":ok}, history=1)
        one, two = observation(), observation(2)
        assert (await pipeline.process(one)).decision == "abstain"
        assert pipeline.get(one.event_id).state == "completed"
        await pipeline.process(two)
        assert pipeline.get(one.event_id) is None
        assert pipeline.get(two.event_id).decision == "abstain"
        assert pipeline.status()["completed"] == 2
        assert pipeline.status()["reports_evicted"] == 1
    asyncio.run(run())

def test_registry_and_transient_retry_policy():
    calls = {}
    async def flaky(o, previous):
        calls[o.event_id] = calls.get(o.event_id, 0) + 1
        if o.sequence == 2 or calls[o.event_id] == 1:
            raise TransientStageError("internal")
        return StageValue(state="completed")
    async def run():
        pipeline = PipelineOrchestrator(overrides={"inference":flaky}, retry_safe=frozenset({"inference"}))
        one, two = observation(), observation(2)
        await pipeline.process(one)
        await pipeline.process(two)
        assert pipeline.get(one.event_id).stages[0].attempts == 2
        assert pipeline.get(one.event_id).stages[0].state == "completed"
        # Real tracking adapter is not installed even when inference returns a test value.
        assert pipeline.get(one.event_id).stages[1].state == "unavailable"
        assert pipeline.get(two.event_id).stages[0].reason == "transient_exhausted"
        assert pipeline.status()["stages"]["inference"]["retries"] == 2
        assert calls == {one.event_id:2,two.event_id:2}
    asyncio.run(run())

def test_breaker_recovery_and_nonretryable_failure(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("src.pipeline.policy.monotonic", lambda: clock[0])
    calls = []
    async def bad_then_good(o, previous):
        calls.append(o.sequence)
        if o.sequence < 4:
            raise RuntimeError("private error")
        return StageValue(state="completed")
    async def run():
        pipeline = PipelineOrchestrator(overrides={"inference":bad_then_good},
            retry_safe=frozenset({"inference"}), breaker_threshold=2, breaker_cooldown=1)
        for n in range(1,4):
            o = observation(n)
            await pipeline.process(o)
            result = pipeline.get(o.event_id).stages[0]
            assert result.reason == ("processor_error" if n < 3 else "circuit_open")
            assert pipeline.get(o.event_id).stages[1].state == "skipped"
        assert calls == [1,2]
        assert pipeline.status()["stages"]["inference"]["circuit"] == "open"
        clock[0] = 2
        assert pipeline.status()["stages"]["inference"]["circuit"] == "half_open"
        await pipeline.process(observation(4))
        assert calls == [1,2,4]
        assert pipeline.status()["stages"]["inference"]["circuit"] == "closed"
        assert pipeline.status()["stages"]["inference"]["retries"] == 0
    asyncio.run(run())

def test_timeout_and_invalid_results_isolate_other_stages():
    async def slow(o, previous):
        await asyncio.sleep(1)
        return StageValue(state="completed")
    async def invalid_type(o, previous):
        return {"state":"completed"}
    async def invalid_count(o, previous):
        return StageValue(state="completed", synthetic_vehicle_count=2)
    async def run():
        for adapter, expected in [(slow,"processor_timeout"),(invalid_type,"processor_error"),
                                  (invalid_count,"processor_error")]:
            p = PipelineOrchestrator(overrides={"inference":adapter}, stage_timeout=.01,
                                     retry_safe=frozenset({"inference"}))
            o = observation()
            await p.process(o)
            r = p.get(o.event_id)
            assert r.stages[0].reason == expected
            assert r.stages[0].attempts == (2 if expected == "processor_timeout" else 1)
            assert r.stages[2].state == "completed"
            assert r.stages[3].state == "completed"
            assert r.decision == "abstain"
    asyncio.run(run())

def test_cancellation_and_concurrent_call():
    async def run():
        entered = asyncio.Event()
        async def blocked(o, previous):
            entered.set()
            await asyncio.Event().wait()
        p = PipelineOrchestrator(overrides={"inference":blocked})
        o = observation()
        task = asyncio.create_task(p.process(o))
        await asyncio.wait_for(entered.wait(), 1)
        assert p.status()["state"] == "processing"
        with pytest.raises(RuntimeError):
            await p.process(observation())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert p.get(o.event_id) is None
        assert p.status()["cancelled"] == 1
        assert p.status()["state"] == "idle"
        assert p.events.read(0, 10)["events"][-1].kind == "cancelled"
    asyncio.run(run())

def test_journal_cursor_gap_and_reset():
    bus = EventBus(capacity=2)
    assert bus.read(0, 2)["events"] == []
    for n in (1,2,3):
        bus.publish(observation(n),"started")
    page = bus.read(0, 1)
    assert page["gap"] and page["next_cursor"] == 2
    assert not bus.read(2, 2)["gap"]
    assert bus.read(2, 2)["next_cursor"] == 3
    assert bus.read(3, 2)["events"] == []
    reset = bus.read(100, 2)
    assert reset["reset"] and reset["gap"]
    assert [e.sequence for e in reset["events"]] == [2,3]
    assert bus.status()["evicted"] == 1
    with pytest.raises(ValueError):
        bus.read(-1, 1)
    with pytest.raises(ValueError):
        bus.read(0, 201)
    with pytest.raises(ValueError):
        EventBus(0)

@pytest.mark.parametrize("kwargs", [
    {"stage_timeout":0}, {"stage_timeout":.2}, {"history":0},
    {"overrides":{"decision":ok}}, {"retry_safe":frozenset({"inference"})},
    {"breaker_threshold":0}, {"breaker_cooldown":0}
])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        PipelineOrchestrator(**kwargs)
