import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect
from src.config import Settings
from src.db import Base
from src.main import create_app

SCENARIO={"cycles":[{"a":20,"b":10},{"a":30,"b":5}]}
VIEWER={"x-si-user":"viewer@example","x-si-roles":"viewer"}
OPERATOR={"x-si-user":"operator@example","x-si-roles":"operator"}
ADMIN={"x-si-user":"admin@example","x-si-roles":"admin"}

def proxy_settings(tmp_path,**kwargs):
    return Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'ops.db'}",
        auth_mode="proxy_headers",**kwargs)

def test_production_requires_external_identity_and_audit():
    url="postgresql+psycopg://traffic:secret@db/traffic"
    with pytest.raises(ValidationError):
        Settings(app_env="production",database_url=url,auth_mode="disabled",
                 allowed_origins="https://traffic.example")
    with pytest.raises(ValidationError):
        Settings(app_env="production",database_url=url,auth_mode="proxy_headers",
                 audit_enabled=False,allowed_origins="https://traffic.example")
    with pytest.raises(ValidationError):
        Settings(app_env="production",database_url=url,auth_mode="proxy_headers",
                 allowed_origins="*")
    valid=Settings(app_env="production",database_url=url,auth_mode="proxy_headers",
                   allowed_origins="https://traffic.example")
    assert valid.auth_mode=="proxy_headers" and valid.audit_enabled is True

def test_proxy_rbac_request_ids_metrics_and_audit(tmp_path):
    app=create_app(proxy_settings(tmp_path))
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        assert client.get("/health/live").status_code==200
        assert client.get("/api/v1/decision/status").status_code==401
        read=client.get("/api/v1/decision/status",headers={**VIEWER,"x-request-id":"req-viewer-0001"})
        assert read.status_code==200
        assert read.headers["x-request-id"]=="req-viewer-0001"

        denied=client.post("/api/v1/decision/simulate",headers=VIEWER,json=SCENARIO)
        assert denied.status_code==403
        assert denied.json()["code"]=="insufficient_role"

        allowed=client.post("/api/v1/decision/simulate",headers={**OPERATOR,"x-request-id":"req-oper-0001"},json=SCENARIO)
        assert allowed.status_code==200
        assert allowed.json()["origin"]=="synthetic"
        assert allowed.headers["x-request-id"]=="req-oper-0001"

        assert client.get("/api/v1/operations/audit",headers=VIEWER).status_code==403
        audit=client.get("/api/v1/operations/audit",headers=ADMIN)
        assert audit.status_code==200
        items=audit.json()["items"]
        assert any(item["actor"]=="viewer@example" and item["outcome"]=="denied" for item in items)
        assert any(item["actor"]=="operator@example" and item["outcome"]=="allowed" and item["method"]=="POST" for item in items)
        assert all("payload" not in item for item in items)

        metrics=client.get("/api/v1/operations/metrics",headers=VIEWER)
        assert metrics.status_code==200
        assert "si_http_requests_total" in metrics.text
        status=client.get("/api/v1/operations/status",headers=VIEWER).json()
        assert status["security"]["credentials_stored"] is False
        assert status["security"]["auth_mode"]=="proxy_headers"
        assert status["observability"]["auth_denied_total"]>=2

def test_mutation_fails_closed_when_audit_table_missing(tmp_path):
    app=create_app(proxy_settings(tmp_path))
    with TestClient(app) as client:
        response=client.post("/api/v1/decision/simulate",headers=OPERATOR,json=SCENARIO)
        assert response.status_code==503
        assert response.json()["code"]=="audit_unavailable"
        assert client.get("/api/v1/decision/status",headers=VIEWER).status_code==200
        status=client.get("/api/v1/operations/status",headers=VIEWER).json()
        assert status["observability"]["audit_failures_total"]>=1

def test_websocket_obeys_proxy_identity_boundary(tmp_path):
    app=create_app(proxy_settings(tmp_path,allowed_origins="http://testserver"))
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/ws/realtime",headers={"origin":"http://testserver"}):
                pass
        with client.websocket_connect("/api/v1/ws/realtime",
                headers={**VIEWER,"origin":"http://testserver"}) as ws:
            assert ws.receive_json()["type"]=="connection_ack"
            ws.send_text("ping")
            assert ws.receive_json()["type"]=="heartbeat"

def test_disabled_auth_preserves_local_compatibility_and_audits_mutation(tmp_path):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'local.db'}")
    app=create_app(settings)
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        assert client.get("/api/v1/decision/status").status_code==200
        assert client.post("/api/v1/decision/simulate",json=SCENARIO).status_code==200
        rows=client.get("/api/v1/operations/audit").json()["items"]
        assert any(item["actor"]=="local-development" and item["method"]=="POST" for item in rows)
