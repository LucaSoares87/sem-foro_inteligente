from datetime import datetime, timezone
from time import monotonic, sleep
from uuid import uuid4
from fastapi.testclient import TestClient
from src.config import Settings
from src.main import create_app

def test_pipeline_via_existing_ingestion_api(tmp_path):
    settings = Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'pipeline.db'}")
    event_id = str(uuid4())
    payload = {"event_id":event_id, "intersection_code":"CR_01", "source_id":"CAM_01",
               "sequence":1, "captured_at":datetime.now(timezone.utc).isoformat(),"vehicle_count":6}
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/pipeline/status")
        assert status.status_code == 200
        assert status.json()["inference_mode"] == "not_loaded"
        assert client.get(f"/api/v1/pipeline/reports/{event_id}").status_code == 404
        r = client.post("/api/v1/ingestion/observations", json=payload)
        assert r.status_code == 202
        deadline = monotonic()+2
        while monotonic()<deadline:
            receipt = client.get(r.headers["Location"]).json()
            if receipt["state"] == "processed":
                break
            sleep(.01)
        assert receipt["state"] == "processed"
        report = client.get(f"/api/v1/pipeline/reports/{event_id}").json()
        assert report["observation"]["event_id"] == event_id
        assert report["state"] == "degraded" and report["decision"] == "abstain"
        assert report["stages"][2]["value"]["synthetic_vehicle_count"] == 6
        events = client.get("/api/v1/pipeline/events?after=0&limit=2").json()
        assert len(events["events"]) == 2 and events["next_cursor"] == 2
        tail = client.get("/api/v1/pipeline/events?after=2").json()
        assert tail["events"][-1]["kind"] == "finished"
        assert client.get("/api/v1/pipeline/events?limit=201").status_code == 422
        assert client.get("/api/v1/pipeline/events?after=-1").status_code == 422
        assert client.post("/api/v1/ingestion/observations",json=payload).status_code == 200
        assert client.get("/api/v1/pipeline/status").json()["degraded"] == 1
        health = client.get("/health").json()
        assert health["pipeline"]["origin"] == "synthetic"
        assert health["ingestion"]["processed"] == 1
        assert health["stream_manager"] == "not_implemented"
        assert health["inference_engine"] == "not_loaded"
        with client.websocket_connect("/api/v1/ws/realtime") as ws:
            assert ws.receive_json()["type"] == "connection_ack"
            ws.send_text("ping")
            assert ws.receive_json()["type"] == "heartbeat"
