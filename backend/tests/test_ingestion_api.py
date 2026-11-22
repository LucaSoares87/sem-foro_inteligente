from datetime import datetime, timezone
from time import monotonic, sleep
from uuid import uuid4
from fastapi.testclient import TestClient
from src.config import Settings
from src.main import create_app

def test_ingestion_api_and_foundation_compatibility(tmp_path):
    settings = Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'ingest.db'}")
    payload = {"event_id":str(uuid4()), "intersection_code":"CR_01",
               "source_id":"CAM_01", "sequence":1,
               "captured_at":datetime.now(timezone.utc).isoformat(), "vehicle_count":4}
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/ingestion/status").json()["status"] == "running"
        assert client.get("/health/live").status_code == 200
        health = client.get("/api/v1/health")
        assert health.status_code == 503
        assert health.json()["ingestion"]["origin"] == "synthetic"
        assert health.json()["stream_manager"] == "not_implemented"
        assert health.json()["inference_engine"] == "not_loaded"
        response = client.post("/api/v1/ingestion/observations", json=payload)
        assert response.status_code == 202
        url = response.headers["Location"]
        deadline = monotonic() + 2
        while monotonic() < deadline:
            receipt = client.get(url).json()
            if receipt["state"] == "processed":
                break
            sleep(.01)
        assert receipt["state"] == "processed"
        assert receipt["observation"]["origin"] == "synthetic"
        assert client.post("/api/v1/ingestion/observations",json=payload).status_code == 200
        assert client.post("/api/v1/ingestion/observations",json={**payload,"vehicle_count":5}).status_code == 409
        assert client.post("/api/v1/ingestion/observations",json={**payload,"origin":"real"}).status_code == 422
        assert client.get(f"/api/v1/ingestion/observations/{uuid4()}").status_code == 404
        with client.websocket_connect("/api/v1/ws/realtime") as ws:
            assert ws.receive_json()["type"] == "connection_ack"
            ws.send_text("ping")
            assert ws.receive_json()["type"] == "heartbeat"
