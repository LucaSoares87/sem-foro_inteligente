import json
from fastapi.testclient import TestClient
import pytest
from src.config import Settings
from src.db import Base
from src.main import create_app
from src.geography.contracts import IntersectionSeed
from src.predictive.history import build_intersection_history
from test_predictive import make_windows

def test_build_history_keeps_sources_directions_and_epochs_separate():
    windows=make_windows(2)
    result=build_intersection_history("CR_01",{"CAM_01":windows})
    assert result["state"]=="available"
    assert result["aggregation_across_sources"] is False
    assert result["operationally_validated"] is False
    assert result["windows"]==2
    assert result["source_ids"]==["CAM_01"]
    assert len(result["series"])==2
    forward=next(x for x in result["series"] if x["direction"]=="negative_to_positive")
    assert [p["observed_passages"] for p in forward["points"]]==[3,3]
    assert all(p["quality"]=="observed" for p in forward["points"])
    limited=windows[1].model_copy(update={"limited_intervals":1})
    mixed=build_intersection_history("CR_01",{"CAM_01":[windows[0],limited]})
    fwd=next(x for x in mixed["series"] if x["direction"]=="negative_to_positive")
    assert fwd["points"][1]["quality"]=="limited"

def test_history_rejects_cross_intersection_contamination():
    window=make_windows(1)[0].model_copy(update={"intersection_code":"CR_02"})
    with pytest.raises(ValueError):
        build_intersection_history("CR_01",{"CAM_01":[window]})

def test_intersection_history_api(tmp_path):
    settings=Settings(app_env="test",archive_enabled=True,
        database_url=f"sqlite:///{tmp_path/'history.sqlite'}",
        video_sources_json=json.dumps([
          {"source_id":"CAM_01","intersection_code":"CR_01","kind":"file","locator":"fixture.avi"}
        ]))
    app=create_app(settings)
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        for window in make_windows(3):
            app.state.history.store.save(window)
        response=client.get("/api/v1/predictive/intersections/CR_01/history?limit=2")
        assert response.status_code==200
        payload=response.json()
        assert payload["windows"]==2
        assert payload["source_ids"]==["CAM_01"]
        assert payload["state"]=="available"
        assert len(payload["series"])==2
        assert client.get("/api/v1/predictive/intersections/UNKNOWN/history").status_code==404
        assert client.get("/api/v1/predictive/intersections/bad value/history").status_code==422

def test_empty_registered_intersection_returns_empty_history(tmp_path):
    settings=Settings(app_env="test",archive_enabled=True,
        database_url=f"sqlite:///{tmp_path/'empty.sqlite'}",
        intersection_registry_json=json.dumps([{"code":"CR_02","name":"Sem câmera"}]))
    app=create_app(settings)
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        app.state.geography.sync((IntersectionSeed(code="CR_02",name="Sem câmera"),))
        response=client.get("/api/v1/predictive/intersections/CR_02/history")
        assert response.status_code==200
        assert response.json()["state"]=="empty"
