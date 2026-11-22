import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from src.config import Settings
from src.main import create_app
from src.db import SCHEMA_REVISION

@pytest.fixture
def settings(tmp_path):
    return Settings(app_env="test", database_url=f"sqlite:///{tmp_path / 'test.db'}")

def test_no_actuation(settings):
    with pytest.raises(ValidationError):
        Settings(app_env="test", database_url=settings.database_url, operation_mode="physical")

def test_readiness_requires_migration(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["inference_engine"] == "not_loaded"
        with app.state.engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": SCHEMA_REVISION})
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/health").json()["stream_manager"] == "not_configured"

def test_websocket(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws/realtime") as ws:
            assert ws.receive_json()["type"] == "connection_ack"
            ws.send_text("ping")
            assert ws.receive_json()["type"] == "heartbeat"
        assert client.get("/health").json()["websocket_connections"] == 0

def test_websocket_rejects_origin(settings):
    from starlette.websockets import WebSocketDisconnect
    with TestClient(create_app(settings)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/ws/realtime", headers={"origin":"https://untrusted.example"}):
                pass
