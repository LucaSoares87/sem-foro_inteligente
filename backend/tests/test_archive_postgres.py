import os
from datetime import datetime, timezone
from time import monotonic, sleep
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from src.config import Settings
from src.main import create_app
from src.archive.store import ArchiveStore
from src.db import make_engine, PipelineArchive
from sqlalchemy import delete

@pytest.mark.skipif(os.getenv("ARCHIVE_POSTGRES_TEST") != "1",reason="requires migrated disposable CI PostgreSQL")
def test_postgres_commit_restart_replay():
    settings = Settings(archive_enabled=True)
    assert settings.db_url().get_backend_name() == "postgresql"
    event_id = str(uuid4())
    body = {"event_id":event_id,"intersection_code":"CI_02C","source_id":"CAM_CI",
            "sequence":1,"captured_at":datetime.now(timezone.utc).isoformat(),"vehicle_count":2}
    try:
        with TestClient(create_app(settings)) as client:
            assert client.get("/health").status_code == 200
            response = client.post("/api/v1/ingestion/observations",json=body)
            assert response.status_code == 202,response.text
            deadline = monotonic()+8
            while monotonic()<deadline:
                receipt = client.get(response.headers["Location"]).json()
                if receipt["state"] in {"processed","failed","cancelled"}:
                    break
                sleep(.02)
            assert receipt["state"] == "processed",receipt
        with TestClient(create_app(settings)) as client:
            assert client.get(f"/api/v1/archive/runs/{event_id}").status_code == 200
            assert len(client.get(f"/api/v1/archive/runs/{event_id}/replay").json()["frames"]) == 7
            assert client.post("/api/v1/ingestion/observations",json=body).status_code == 200
    finally:
        engine = make_engine(settings)
        try:
            with engine.begin() as connection:
                connection.execute(delete(PipelineArchive).where(PipelineArchive.event_id==event_id))
        finally:
            engine.dispose()
