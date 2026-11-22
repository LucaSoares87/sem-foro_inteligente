import json
from sqlalchemy import create_engine,text
from fastapi.testclient import TestClient
import pytest
from src.config import Settings
from src.db import Base,SCHEMA_REVISION
from src.geography.contracts import IntersectionSeed,load_registry
from src.geography.store import GeographyStore
from src.main import create_app

def migrated_db(path):
    url=f"sqlite:///{path}"
    engine=create_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"),{"revision":SCHEMA_REVISION})
    engine.dispose()
    return url

def test_registry_validation():
    valid=[{"code":"CR_01","name":"Av. A x Av. B","district":"Centro",
            "latitude":-8.05,"longitude":-34.9,"enabled":True},
           {"code":"CR_02","name":"Sem coordenadas"}]
    values=load_registry(json.dumps(valid))
    assert len(values)==2
    assert values[0].latitude==-8.05
    assert values[1].latitude is None
    for invalid in [
        "{}", "not json",
        json.dumps([valid[0],valid[0]]),
        json.dumps([{"code":"cr 1","name":"Inválido"}]),
        json.dumps([{"code":"CR_01","name":"Inválido","latitude":-8.0}]),
        json.dumps([{"code":"CR_01","name":"Inválido","latitude":91,"longitude":0}])
    ]:
        with pytest.raises(ValueError,match="invalid intersection registry"):
            load_registry(invalid)

def test_store_upsert_filters_and_never_deletes_implicitly(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'geo.db'}")
    Base.metadata.create_all(engine)
    store=GeographyStore(engine)
    store.sync((
        IntersectionSeed(code="CR_01",name="Primeiro",district="Centro",latitude=-8,longitude=-35),
        IntersectionSeed(code="CR_02",name="Segundo",enabled=False),
    ))
    assert [x.code for x in store.list()]==["CR_01"]
    assert [x.code for x in store.list(include_disabled=True)]==["CR_01","CR_02"]
    assert [x.code for x in store.list(with_coordinates=True)]==["CR_01"]
    assert [x.code for x in store.list(include_disabled=True,with_coordinates=False)]==["CR_02"]
    assert [x.code for x in store.list(district="Centro")]==["CR_01"]
    store.sync((IntersectionSeed(code="CR_01",name="Atualizado",district="Norte"),))
    assert store.get("CR_01").name=="Atualizado"
    assert store.get("CR_01").latitude is None
    assert store.get("CR_02") is None
    assert store.get("CR_02",include_disabled=True).name=="Segundo"
    engine.dispose()

def test_startup_sync_api_and_health(tmp_path):
    url=migrated_db(tmp_path/"app.db")
    registry=json.dumps([
        {"code":"CR_01","name":"Av. A x Av. B","district":"Centro","latitude":-8.052,"longitude":-34.901},
        {"code":"CR_02","name":"Cruzamento sem coordenadas","enabled":True},
        {"code":"CR_OFF","name":"Desativado","enabled":False}
    ])
    settings=Settings(app_env="test",database_url=url,intersection_registry_json=registry)
    with TestClient(create_app(settings)) as client:
        health=client.get("/health")
        assert health.status_code==200
        assert health.json()["geography"]=={
            "state":"available","configured":3,"synced":3,"error_code":None,
            "coordinate_system":"WGS84","external_map_service":False}
        rows=client.get("/api/v1/intersections").json()
        assert [r["code"] for r in rows]==["CR_01","CR_02"]
        assert rows[0]["has_coordinates"] is True
        assert rows[1]["has_coordinates"] is False
        assert client.get("/api/v1/intersections?with_coordinates=true").json()[0]["code"]=="CR_01"
        assert client.get("/api/v1/intersections?district=Centro").json()[0]["code"]=="CR_01"
        assert client.get("/api/v1/intersections?include_disabled=true").json()[-1]["code"]=="CR_OFF"
        assert client.get("/api/v1/intersections/CR_01").json()["name"]=="Av. A x Av. B"
        assert client.get("/api/v1/intersections/CR_OFF").status_code==404
        assert client.get("/api/v1/intersections/CR_OFF?include_disabled=true").status_code==200
        assert client.get("/api/v1/intersections/UNKNOWN").status_code==404

def test_invalid_registry_degrades_readiness_without_crashing(tmp_path):
    url=migrated_db(tmp_path/"invalid.db")
    settings=Settings(app_env="test",database_url=url,intersection_registry_json='{"bad":true}')
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code==200
        health=client.get("/health")
        assert health.status_code==503
        assert health.json()["geography"]["error_code"]=="registry_config_invalid"
        assert client.get("/api/v1/intersections").status_code==200
