import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic, sleep
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from src.archive.contracts import ArchivedRun
from src.archive.store import ArchiveIntegrityError, ArchiveStore, fingerprint
from src.config import Settings
from src.db import Base, PipelineArchive, SCHEMA_REVISION
from src.ingestion.engine import DuplicateConflict
from src.main import create_app
from src.pipeline.events import EventBus
from src.pipeline.orchestrator import PipelineOrchestrator

def payload(event_id=None, intersection="CR_01"):
    return {"event_id":str(event_id or uuid4()), "intersection_code":intersection,
            "source_id":"CAM_01", "sequence":1, "captured_at":datetime.now(timezone.utc).isoformat(),
            "vehicle_count":4}

def submit_and_wait(client, body):
    response = client.post("/api/v1/ingestion/observations",json=body)
    assert response.status_code == 202, response.text
    deadline = monotonic()+5
    while monotonic()<deadline:
        receipt = client.get(response.headers["Location"]).json()
        if receipt["state"] in {"processed","failed","cancelled"}:
            return receipt
        sleep(.01)
    pytest.fail("worker did not finish")

@pytest.fixture
def setup(tmp_path):
    settings = Settings(app_env="test", archive_enabled=True, database_url=f"sqlite:///{tmp_path/'archive.db'}")
    engine = create_engine(settings.db_url())
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"),{"revision":SCHEMA_REVISION})
    yield settings,engine
    engine.dispose()

def test_archive_restart_idempotency_replay_and_epoch(setup):
    settings,engine = setup
    one,two = payload(),payload(intersection="CR_02")
    event_id = one["event_id"]
    url = f"/api/v1/archive/runs/{event_id}"
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["archive"]["status"] == "available"
        assert submit_and_wait(client,one)["state"] == "processed"
        assert submit_and_wait(client,two)["state"] == "processed"
        whole = client.get(url).json()
        assert whole["receipt"]["state"] == "processed"
        assert client.get(f"/api/v1/ingestion/observations/{event_id}").json() == whole["receipt"]
        assert whole["report"]["decision"] == "abstain"
        assert len(whole["events"]) == 7
        epoch = client.get("/api/v1/pipeline/events").json()["epoch"]
        assert epoch == whole["journal_epoch"]
        archive_page = client.get("/api/v1/archive/runs?limit=1").json()
        assert archive_page["has_more"] and archive_page["items"][0]["event_id"] == event_id
        assert client.get("/api/v1/archive/runs",params={"after":archive_page["next_cursor"]}).json()["items"][0]["event_id"] == two["event_id"]
        assert len(client.get("/api/v1/archive/runs?intersection=CR_02").json()["items"]) == 1
        assert client.get("/api/v1/archive/runs?limit=101").status_code == 422
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/v1/ingestion/observations/{event_id}").json() == whole["receipt"]
        assert client.get(f"/api/v1/pipeline/reports/{event_id}").json() == whole["report"]
        assert client.post("/api/v1/ingestion/observations",json=one).status_code == 200
        assert client.post("/api/v1/ingestion/observations",json={**one,"vehicle_count":5}).status_code == 409
        assert client.get("/api/v1/ingestion/status").json()["accepted"] == 0
        before = client.get("/api/v1/pipeline/status").json()
        replay = client.get(url+"/replay").json()
        assert replay["mode"] == "read_only" and replay["decision"] == "abstain"
        assert replay["journal_epoch"] == epoch and replay["frames"][0]["offset_ms"] == 0
        assert [x["event"] for x in replay["frames"]] == whole["events"]
        assert client.get("/api/v1/pipeline/status").json() == before
        reset = client.get("/api/v1/pipeline/events",params={"after":0,"epoch":epoch}).json()
        assert reset["reset"] and reset["gap"] and reset["epoch"] != epoch
        assert client.get(f"/api/v1/archive/runs/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/pipeline/reports/{uuid4()}").status_code == 404
        assert client.get(f"/api/v1/ingestion/observations/{uuid4()}").status_code == 404
    store = ArchiveStore(engine)
    run = store.get(event_id)
    assert store.save(run) == run
    with pytest.raises(DuplicateConflict):
        changed = run.report.observation.model_copy(update={"vehicle_count":9})
        store.save(run.model_copy(update={"report":run.report.model_copy(update={"observation":changed}),
                                          "receipt":run.receipt.model_copy(update={"observation":changed})}))

def test_corruption_and_retention(setup):
    settings,engine = setup
    body = payload()
    with TestClient(create_app(settings)) as client:
        assert submit_and_wait(client,body)["state"] == "processed"
    store = ArchiveStore(engine)
    cutoff = datetime.now(timezone.utc)+timedelta(days=1)
    assert store.retention(cutoff) == 1
    with Session(engine) as session:
        row = session.scalar(select(PipelineArchive))
        row.digest = "0"*64
        session.commit()
    with pytest.raises(ArchiveIntegrityError):
        store.get(body["event_id"])
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/v1/archive/runs/{body['event_id']}").status_code == 503
        assert client.get("/api/v1/archive/runs").status_code == 503
        assert client.get(f"/api/v1/pipeline/reports/{body['event_id']}").status_code == 503
        assert client.get(f"/api/v1/ingestion/observations/{body['event_id']}").status_code == 503
        assert client.post("/api/v1/ingestion/observations",json=body).status_code == 503
    assert store.retention(cutoff,apply=True) == 1
    assert store.get(body["event_id"]) is None
    with pytest.raises(ValueError):
        store.retention(datetime.now())

def test_missing_schema_fail_closed_and_disabled_explicitly(tmp_path):
    db = f"sqlite:///{tmp_path/'missing.db'}"
    enabled = Settings(app_env="test",archive_enabled=True,database_url=db)
    with TestClient(create_app(enabled)) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/health").json()["archive"]["status"] == "unavailable"
        assert client.post("/api/v1/ingestion/observations",json=payload()).status_code == 503
        assert client.get("/api/v1/ingestion/status").json()["accepted"] == 0
    disabled = Settings(app_env="test",database_url=db)
    with TestClient(create_app(disabled)) as client:
        assert client.get("/health").json()["archive"]["status"] == "disabled"
        assert submit_and_wait(client,payload())["state"] == "processed"
        assert client.get("/api/v1/archive/runs").status_code == 503
        assert client.get(f"/api/v1/archive/runs/{uuid4()}").status_code == 503

def test_failed_write_not_processed(setup,monkeypatch):
    settings,engine = setup
    def fail(self,run):
        raise ArchiveIntegrityError("private details")
    monkeypatch.setattr(ArchiveStore,"save",fail)
    with TestClient(create_app(settings)) as client:
        body = payload()
        receipt = submit_and_wait(client,body)
        assert receipt["state"] == "failed" and receipt["error_code"] == "processor_error"
        assert client.get(f"/api/v1/archive/runs/{body['event_id']}").status_code == 404
        assert client.get(f"/api/v1/pipeline/reports/{body['event_id']}").status_code == 404

def test_integrity_validation(setup):
    settings,engine = setup
    body = payload()
    with TestClient(create_app(settings)) as client:
        assert submit_and_wait(client,body)["state"] == "processed"
    with Session(engine) as session:
        row = session.scalar(select(PipelineArchive))
        altered = {**row.payload,"events":row.payload["events"][:1]}
        row.payload = altered
        row.digest = fingerprint(altered)
        session.commit()
    with pytest.raises(ArchiveIntegrityError):
        ArchiveStore(engine).get(body["event_id"])
