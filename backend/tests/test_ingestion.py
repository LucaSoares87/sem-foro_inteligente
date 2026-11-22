import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError
from src.ingestion.contracts import Handoff, Observation
from src.ingestion.engine import DuplicateConflict, IngestionEngine, IngestionUnavailable

def event(n=0, source="CAM_01", intersection="CR_01"):
    return Observation(event_id=uuid4(), intersection_code=intersection,
        source_id=source, sequence=n, captured_at=datetime.now(timezone.utc), vehicle_count=3)

def assert_balance(engine):
    s = engine.status()
    assert s["accepted"] == sum(s[k] for k in ("queued","in_flight","processed","failed","cancelled"))

@pytest.mark.parametrize("update", [
    {"origin":"real"}, {"vehicle_count":-1}, {"vehicle_count":True},
    {"sequence":-1}, {"captured_at":"2026-01-01T00:00:00"},
    {"source_id":"rtsp://secret"}, {"unknown":1}, {"schema_version":2},
])
def test_contract_rejects_invalid_input(update):
    with pytest.raises(ValidationError):
        Observation.model_validate({**event().model_dump(), **update})

def test_contract_provenance_and_immutability():
    observation = event()
    assert observation.origin == "synthetic"
    with pytest.raises(ValidationError):
        observation.vehicle_count = 99
    with pytest.raises(ValidationError):
        Handoff(observation=observation, decision="green")

def test_queue_idempotency_and_order():
    async def run():
        received = []
        async def processor(o):
            received.append(o)
            return Handoff(observation=o)
        e = IngestionEngine(capacity=2, processor=processor)
        first, second, third = event(1), event(2, "CAM_02","CR_02"), event(3)
        with pytest.raises(IngestionUnavailable):
            e.submit(first)
        e.start()
        with pytest.raises(RuntimeError):
            e.start()
        assert e.submit(first)[1] is False
        assert e.submit(first)[1] is True
        with pytest.raises(DuplicateConflict):
            e.submit(first.model_copy(update={"vehicle_count":4}))
        e.submit(second)
        with pytest.raises(IngestionUnavailable):
            e.submit(third)
        assert_balance(e)
        await e.wait_idle()
        assert received == [first, second]
        assert e.get(first.event_id).state == "processed"
        assert e.submit(first)[1] is True
        assert e.status()["last_processing_ms"] >= 0
        assert e.status()["rejected"] == 2
        assert e.status()["duplicates"] == 2
        assert e.status()["conflicts"] == 1
        await e.stop()
        await e.stop()
        assert_balance(e)
        assert e.status()["status"] == "stopped"
    asyncio.run(run())

def test_failure_timeout_and_invalid_handoff_do_not_block_next_event():
    async def processor(o):
        if o.sequence == 1:
            raise RuntimeError("secret-not-returned")
        if o.sequence == 2:
            await asyncio.sleep(2)
        if o.sequence == 3:
            return Handoff(observation=event(99))
        return Handoff(observation=o)
    async def run():
        e = IngestionEngine(capacity=4, timeout=.03, processor=processor)
        e.start()
        items = [event(i) for i in range(1,5)]
        for item in items:
            e.submit(item)
        await e.stop()
        assert [e.get(o.event_id).error_code for o in items] == [
            "processor_error","processor_timeout","processor_error",None]
        assert e.get(items[-1].event_id).state == "processed"
        assert e.status()["failed"] == 3
        assert_balance(e)
    asyncio.run(run())

def test_shutdown_cancels_pending_work():
    async def run():
        entered = asyncio.Event()
        async def processor(o):
            entered.set()
            await asyncio.Event().wait()
        e = IngestionEngine(capacity=2, timeout=5, drain_timeout=.02, processor=processor)
        e.start()
        items = [event(1), event(2)]
        for item in items:
            e.submit(item)
        await asyncio.wait_for(entered.wait(), 1)
        await e.stop()
        assert all(e.get(o.event_id).state == "cancelled" for o in items)
        assert e.status()["cancelled"] == 2
        assert_balance(e)
        e.start()
        await e.stop()
    asyncio.run(run())

def test_history_bounded():
    async def run():
        e = IngestionEngine(history=1)
        e.start()
        first, second = event(1), event(2)
        for item in (first, second):
            e.submit(item)
            await e.wait_idle()
        assert e.get(first.event_id) is None
        assert e.get(second.event_id) is not None
        assert e.status()["history_evicted"] == 1
        await e.stop()
        assert_balance(e)
    asyncio.run(run())

@pytest.mark.parametrize("kwargs", [{"capacity":0},{"history":0},{"timeout":0},{"drain_timeout":0}])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        IngestionEngine(**kwargs)
