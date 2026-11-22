import itertools
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from src.config import Settings
from src.main import create_app
from src.decision.contracts import CycleDemand,SimulationScenario
from src.decision.engine import compare,simulate,allocate,BUDGET,MIN_SERVICE,MAX_SERVICE,MAX_CHANGE,FIXED,CYCLE
from src.decision.service import PRESETS,scenario_for,eligibility,status

def scenario(pairs,initial_a=0,initial_b=0):
    return SimulationScenario(cycles=tuple(CycleDemand(a=a,b=b) for a,b in pairs),
        initial_a=initial_a,initial_b=initial_b)

@pytest.mark.parametrize("preset",PRESETS)
def test_presets_conservation_and_constraints(preset):
    s=scenario_for(preset)
    r=compare(s)
    assert r==compare(s)
    assert r.origin=="synthetic" and r.physical_actuation is False
    assert r.operationally_validated is False
    assert r.fixed.arrivals==r.adaptive.arrivals==sum(c.a+c.b for c in s.cycles)
    for result in (r.fixed,r.adaptive):
        qa,qb=s.initial_a,s.initial_b
        previous=FIXED
        for c,demand in zip(result.cycles,s.cycles):
            assert c.arrivals_a==demand.a and c.arrivals_b==demand.b
            assert MIN_SERVICE<=c.service_a_ticks<=MAX_SERVICE
            assert MIN_SERVICE<=c.service_b_ticks<=MAX_SERVICE
            assert c.service_a_ticks+c.service_b_ticks==BUDGET
            assert c.service_a_ticks+c.service_b_ticks+c.idle_ticks==CYCLE
            assert abs(c.service_a_ticks-previous)<=MAX_CHANGE
            assert c.end_a==qa+c.arrivals_a-c.served_a
            assert c.end_b==qb+c.arrivals_b-c.served_b
            assert c.end_a>=0 and c.end_b>=0
            assert 0<=c.served_a<=2*c.service_a_ticks
            assert 0<=c.served_b<=2*c.service_b_ticks
            qa,qb=c.end_a,c.end_b
            previous=c.service_a_ticks
        assert result.final_queue==result.initial_queue+result.arrivals-result.served
        assert result.queue_area==sum(c.queue_area for c in result.cycles)
        assert result.queue_area==result.queue_area_a+result.queue_area_b
        assert result.peak_combined==max(c.peak_combined for c in result.cycles)

def test_causality_and_saturation():
    a=scenario([(15,15),(70,5),(0,0)])
    b=scenario([(15,15),(5,70),(120,120)])
    r1,r2=simulate(a,"adaptive"),simulate(b,"adaptive")
    assert r1.cycles[0]==r2.cycles[0]
    assert r1.cycles[1].service_a_ticks==r2.cycles[1].service_a_ticks
    for qa,qb,previous in itertools.product([0,1,10000],[0,1,10000],range(MIN_SERVICE,MAX_SERVICE+1)):
        current=allocate(qa,qb,(0,0),previous)
        assert MIN_SERVICE<=current<=MAX_SERVICE
        assert abs(current-previous)<=MAX_CHANGE
    assert allocate(0,0,(0,0),FIXED)==FIXED
    with pytest.raises(ValueError):
        simulate(a,"unknown")

def test_selection_and_empty():
    empty=compare(scenario([(0,0)]*2))
    assert empty.preferred_in_simulation=="equivalent"
    assert empty.reason=="equal_outcomes"
    assert empty.queue_area_reduction_pct is None
    one=compare(scenario([(90,0)]*8))
    assert one.preferred_in_simulation=="adaptive"
    assert one.queue_area_reduction_pct>0
    assert one.reason=="lower_queue_area_without_regression"
    # Serving A for longer increases queue-area of B with at least some traffic.
    tradeoff=compare(scenario([(90,10)]*8))
    assert tradeoff.preferred_in_simulation=="fixed"
    assert tradeoff.reason=="adaptive_tradeoff_or_no_gain"
    assert one.result_sha256!=tradeoff.result_sha256
    assert one.scenario_sha256!=tradeoff.scenario_sha256

def test_initial_queue_and_overload():
    r=compare(scenario([(120,120)]*20,200,200))
    for x in (r.fixed,r.adaptive):
        assert x.initial_queue==400
        assert x.final_queue>400
        assert x.final_queue+x.served==x.arrivals+400

@pytest.mark.parametrize("body",[
    {"origin":"real","cycles":[{"a":0,"b":0}]*2},
    {"cycles":[{"a":0,"b":0}]},
    {"cycles":[{"a":0,"b":0}]*21},
    {"cycles":[{"a":-1,"b":0}]*2},
    {"cycles":[{"a":121,"b":0}]*2},
    {"cycles":[{"a":True,"b":0}]*2},
    {"cycles":[{"a":0,"b":0}]*2,"controller":"hardware"},
])
def test_contract_rejects_invalid(body):
    with pytest.raises(ValueError):
        SimulationScenario.model_validate(body)

def test_eligibility_never_uses_unvalidated_data():
    history=SimpleNamespace(status=lambda:{"state":"available"})
    for current in (None,SimpleNamespace(purpose="authorized_candidate",analytics_epoch=uuid4())):
        analytics=SimpleNamespace(latest=lambda s:current)
        result=eligibility(analytics,history,"CAM_01")
        assert result["state"]=="abstain" and not result["physical_actuation"]
        assert result["snapshot_available"]==(current is not None)
        assert result["reason"]==("visual_data_not_operationally_validated" if current else "no_current_analytics")
        assert "approved_intersection_geometry_and_conflicts" in result["missing_evidence"]
    assert status()["operational_decision"]=="abstain"

def test_api_and_health(tmp_path):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'db.sqlite'}",
       video_sources_json=json.dumps([{"source_id":"CAM_01","intersection_code":"CR_01","kind":"file","locator":"fixture.avi"}]))
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/decision/status").json()["operational_decision"]=="abstain"
        r=client.get("/api/v1/decision/demo?preset=surge")
        assert r.status_code==200
        assert r.json()["origin"]=="synthetic"
        response=client.post("/api/v1/decision/simulate",json=r.json()["scenario"])
        assert response.status_code==200 and response.json()==r.json()
        assert client.get("/api/v1/decision/demo?preset=real").status_code==422
        assert client.get("/api/v1/decision/sources/UNKNOWN/eligibility").status_code==404
        assert client.get("/api/v1/decision/sources/CAM_01/eligibility").json()["state"]=="abstain"
        assert client.get("/health/live").status_code==200
        health=client.get("/health").json()
        assert health["decision"]["physical_actuation"] is False
        assert health["ingestion"]["accepted"]==0
        assert health["inference_engine"]=="not_loaded"
        with client.websocket_connect("/api/v1/ws/realtime") as ws:
            assert ws.receive_json()["type"]=="connection_ack"
            ws.send_text("ping")
            assert ws.receive_json()["type"]=="heartbeat"
