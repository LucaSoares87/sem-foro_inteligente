"""Direct acceptance regression for each original requirement; PASS != field approval."""
from collections import deque
from itertools import product
from pathlib import Path
import json
import pytest
from src.benchmarking import pimcat_local as l, pimcat_midblock as m
from src.benchmarking import pimcat_c2_sumo as c2, pimcat_d_sumo as d, pimcat_e_global as e
from src.benchmarking.pimcat_c3_vision import Geometry, Person, Perception
from src.benchmarking.pimcat_c3_study import blank_reference, independent_metrics
from src.optimization.engine import evaluate
from src.benchmarking.si11c_predictive_x import observed

ROOT=Path(__file__).resolve().parents[2]
MATRIX=json.loads((ROOT/"docs/pimcat/g-scenarios.json").read_text())
LEDGER=json.loads((ROOT/"frontend/src/app/pimcatEvidence.json").read_text())
def study(key):return next(s for s in LEDGER["studies"] if s["key"]==key)
def abstract(name,policy="integrated_xp_no_xv"):
    s=l.scenario(name);a=l.simulate(policy,s,*l.streams(name,6000))
    assert a["vehicle_arrivals"]==a["vehicle_departed"]+a["vehicle_remaining"]
    assert a["pedestrian_arrivals"]==a["pedestrian_completed"]+a["pedestrian_waiting"]+a["pedestrian_crossing"]
    assert not a["conflict_violations"]
    return a
def rp(**kw):
    args=dict(now=100,waiting="empty",crossing="clear",phase="vehicle",topology_confirmed=True,clearance_complete=True)
    args.update(kw);v=m.assess(**args)
    assert v.operational_decision=="abstain" and not v.physical_actuation and not v.operationally_validated
    return v
def perception():
    return Perception(Geometry("midblock",((.1,.1,.4,.5),),(.4,.1,.8,.5)))
PERSON=Person((.2,.2,.3,.4),.9)

@pytest.fixture(scope="module")
def microscopic(tmp_path_factory):
    root=tmp_path_factory.mktemp("g-sumo");api=c2.ensure_version()
    # Selected previously registered cases. Not independent efficacy evidence.
    return {
        "empty":c2.case(api,root/"empty","mid_empty",7100,("predictive_xp",)),
        "single":c2.case(api,root/"single","mid_single",7100,("predictive_xp",)),
        "corridor":d.case(api,root/"corridor","three_storage",8100,("independent","adaptive_eta_storage")),
        "grid":e.case(api,root/"grid","outage",9100,("local_pressure","global_storage")),
    }

def test_scenario_01_ambos_vazios():
    for last in (0,1):assert l.demand_preference(("empty","empty"),last)==(last,"hold_last")
    assert abstract("empty")["phase_changes"]==0

def test_scenario_02_fluxo_unico():
    for last in (0,1):
        assert l.demand_preference(("demand","empty"),last)==(0,"single_demand")
        assert l.demand_preference(("empty","demand"),last)==(1,"single_demand")
    assert abstract("single_a")["vehicle_departed"]>0

def test_scenario_03_chegada_no_fechado():
    v=abstract("emergence_b")
    assert v["vehicle_departed"]>0 and all(p["phase"]=="B" for p in v["plans"][3:])

def test_scenario_04_filas_equivalentes():
    q=[deque([0]*6),deque([0]*6)]
    for last in (0,1):assert l.proportional(q,(.2,.2),last)==last
    assert abstract("balanced")["vehicle_departed"]>0

def test_scenario_05_filas_assimetricas():
    for policy in ("proportional","integrated_xp"):
        assert abstract("asymmetric_a",policy)["vehicle_departed"]>0
    result=evaluate(observed(((0,.3,.8,40),(0,.1,.8,40)),[deque([0]*12),deque([0]*3)],40))
    assert result.operational_decision=="abstain" and not result.physical_actuation
    assert study("si11d")["research_gate_passed"] is False

def test_scenario_06_dominante_continuo():
    a=abstract("asymmetric_a")
    assert a["vehicle_area"]>0 and a["vehicle_max_wait"]>=0
    assert a["vehicle_p95_departed"] is not None

def test_scenario_07_privacao_minoritaria():
    a=abstract("simultaneous_deadlines")
    assert a["vehicle_deadline_violations"]>0 and a["vehicle_remaining"]>0
    assert a["vehicle_max_wait"]>l.VEH_LIMIT
    assert study("e")["research_gate_passed"] is False

def test_scenario_08_pedestre_isolado():
    a=abstract("isolated_ped")
    assert a["pedestrian_arrivals"]==a["pedestrian_completed"]==1
    assert rp(waiting="demand").oldest_request==100

def test_scenario_09_grupo_progressivo():
    old=l.latch_request(None,0,"demand")
    for t,state in enumerate(("demand","unknown","empty")*50,1):
        assert l.latch_request(old,t,state)==0
    p=perception();p.update(0,[PERSON])
    assert p.update(.2,[PERSON])["oldest_observed_wait_seconds"]==.2
    assert p.update(2,[],available=False)["oldest_observed_wait_seconds"]==2

def test_scenario_10_intenso_120():
    q=[deque([0]*20),deque([0]*2)]
    phase,reason,_=l.choose("integrated_xp_no_xv",l.scenario("intense_120"),q,deque([(0,0,.9)]),0,80)
    assert (phase,reason)==("BP","pedestrian_deadline")
    a=abstract("intense_120")
    assert 0<=a["pedestrian_deadline_violations"]<=a["pedestrian_arrivals"]

def test_scenario_11_oportunidade_antecipada():
    q=[deque(),deque([0]*20)];p=deque([(0,0,.9)])
    phase,reason,_=l.choose("compatible",l.scenario("compatible"),q,p,0,10)
    assert phase=="BP" and reason=="compatible"
    a=abstract("incompatible");assert not a["compatible_admissions"]

def test_scenario_12_mobilidade_reduzida():
    s=l.scenario("slow_crossing");a=[[0,0,0] for _ in range(l.HORIZON)];a[86][2]=1
    v=l.simulate("fixed",s,a,[[1,1]]*l.HORIZON,[.4]*l.HORIZON)
    assert v["pedestrian_completed"]==1 and v["extension_ticks"]>0 and v["protection_blocks"]>0

def test_scenario_13_faixa_ocupada():
    for waiting,phase,clear,old in product(("empty","demand","unknown"),("vehicle","pedestrian","transition","unknown"),(True,False),(None,0)):
        v=rp(waiting=waiting,phase=phase,crossing="occupied",clearance_complete=clear,oldest_request=old)
        assert v.preference_in_simulation=="preserve_protection"
    for phase in ("vehicle","pedestrian","transition","unknown"):
        assert rp(phase=phase,clearance_complete=False).preference_in_simulation=="preserve_protection"

def test_scenario_14_pelotao_anterior(microscopic):
    for v in microscopic["corridor"]["metrics"].values():
        assert v["eta_issued"]==v["eta_arrived"]+v["eta_censored"]
        assert v["eta_covered"]<=v["eta_arrived"]
    assert study("d")["research_gate_passed"] is False

def test_scenario_15_destino_saturado():
    for capacity in range(1,40):
        assert d.capacity_block(capacity,capacity,0)
    a=e.Reading(100,8,8,10,0);full=e.Reading(100,10,10,10,0);empty=e.Reading(100,0,0,10,0)
    for policy in e.POLICIES:
        phase,_=e.arbitrate(policy,False,"A",20,100,{"A":(a,full),"B":(a,empty)},{"A":.5,"B":.5},0,None,{"A":179,"B":0})
        assert phase!="A"
    assert study("e")["gates"]["global_storage/strict_spillback_prevention"] is False

def test_scenario_16_propagacao_3mais(microscopic):
    row=microscopic["grid"];assert row["nodes"]==7 and row["conflicts_verified"]
    for v in row["metrics"].values():
        assert v["vehicle_scheduled"]==v["vehicle_exited"]+v["vehicle_remaining"]+v["vehicle_uninserted"]
        assert v["pedestrian_scheduled"]==v["pedestrian_exited"]+v["pedestrian_remaining"]+v["pedestrian_uninserted"]
        assert v["conflict_violations"]==v["red_entries"]==v["collisions"]==0
        assert v["critical_exposure"]>=0

def test_scenario_17_prazos_simultaneos():
    q=[deque([0]*20),deque([0]*20)]
    p=deque([(0,0,.9)])
    phase,_,_=l.choose("integrated_xp_no_xv",l.scenario("simultaneous_deadlines"),q,p,0,180)
    assert phase in ("A","B","P")
    assert abstract("simultaneous_deadlines")["pedestrian_deadline_violations"]>0

def test_scenario_18_falha_camera():
    assert l.classify(0,.99,0,available=False)=="unknown"
    p=perception();r=p.update(0,[],available=False)
    assert r["crossing"]==r["demand"]=="unknown" and r["waiting_observed"] is None
    assert rp(waiting="unknown",crossing="unknown").preference_in_simulation=="abstain"

def test_scenario_19_falha_comunicacao():
    cohort=d.forecast(10,7,100)
    assert d.upcoming([cohort],33,9)==0 and d.upcoming([cohort],10,9,available=False) is None
    assert e.criticity(e.Reading(10,1,0,10,3),16)==(None,"unknown")

def test_scenario_20_perda_central(microscopic):
    v=microscopic["grid"]["metrics"]["global_storage"]
    assert v["fallback_ticks"]==180
    snap=next(s for s in v["snapshots"] if s["tick"]==240)
    assert not snap["central_available"] and all(r["index"] is None and r["level"]=="unknown" for r in snap["edges"].values())
    a=e.Reading(100,8,8,10,0);empty=e.Reading(100,0,0,10,0)
    local={"A":(a,empty),"B":(empty,a)}
    args=(False,"A",20,100,local,None,0,None,{"A":0,"B":0})
    assert e.arbitrate("global_storage",*args)==e.arbitrate("local_pressure",*args)

def test_scenario_21_baixa_confianca():
    for c in (0,.2,.64,float("nan")):assert l.classify(0,c,0)=="unknown"
    p=perception();p.update(0,[PERSON])
    r=p.update(.2,[Person(PERSON.box,.15)])
    assert r["uncertain"] and r["demand"]=="possible" and r["oldest_observed_wait_seconds"]==.2

def test_scenario_22_oclusao():
    p=perception();p.update(0,[PERSON])
    r=p.update(2,[],occluded=True)
    assert r["demand"]=="possible" and r["crossing"]=="unknown" and r["oldest_observed_wait_seconds"]==2
    assert independent_metrics({},blank_reference("a"*64),blank_reference("a"*64),"reviewer","a"*64) is None
    assert LEDGER["c3_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"

def test_scenario_23_alternancia_excessiva():
    a=e.Reading(100,8,8,10,0);empty=e.Reading(100,0,0,10,0)
    local={"A":(a,empty),"B":(a,empty)}
    for policy,age in product(e.POLICIES,range(12)):
        assert e.arbitrate(policy,False,"A",age,100,local,None,1,0,{"A":0,"B":180})[0]=="A"
    v=abstract("group_ped")
    assert v["phase_changes"]<=l.HORIZON//l.BLOCK

def test_scenario_24_reinicio():
    p=perception();p.update(0,[PERSON])
    assert p.update(.2,[PERSON])["oldest_observed_wait_seconds"]==.2
    fresh=perception().update(0,[])
    assert fresh["demand"]==fresh["crossing"]=="unknown" and fresh["oldest_observed_wait_seconds"] is None
    assert fresh["operational_decision"]=="abstain"
    assert rp(waiting="unknown",crossing="unknown",phase="unknown").preference_in_simulation=="abstain"

def test_scenario_25_fps():
    for fps in (30,15,10,5):
        p=perception()
        for i in range(2*fps+1):r=p.update(i/fps,[PERSON])
        assert r["intention"]=="candidate" and r["oldest_observed_wait_seconds"]==2
    assert {r[0] for r in study("c3")["rows"]}=={"30","15","10","5"}
    assert LEDGER["c3_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"

def test_scenario_26_rp07_sem_demanda(microscopic):
    for t in range(86400):assert rp(now=t).preference_in_simulation=="hold_vehicle_preference"
    v=microscopic["empty"]["metrics"]["predictive_xp"]
    assert v["pedestrians_scheduled"]==0 and v["phase_changes"]==0
    assert v["green_ticks"]["A"]==c2.HORIZON

def test_scenario_27_rp07_pedido_retorno(microscopic):
    v=microscopic["single"]["metrics"]["predictive_xp"]
    assert v["pedestrians_scheduled"]==v["pedestrians_completed"]==1
    assert v["pedestrian_max_wait"]<=120 and v["conflict_violations"]==0
    assert rp(button=True).preference_in_simulation=="evaluate_protected_service"
    assert rp(phase="pedestrian",crossing="occupied",oldest_request=10).preference_in_simulation=="preserve_protection"
    assert rp(phase="pedestrian",oldest_request=10,all_prior_requests_admitted=True).preference_in_simulation=="evaluate_vehicle_return"

def test_cross_module_invariants_and_matrix():
    assert [s["number"] for s in MATRIX["scenarios"]]==list(range(1,28))
    assert {s["test"] for s in MATRIX["scenarios"]}=={k.removeprefix("test_") for k in globals() if k.startswith("test_scenario_")}
    for left,right,last in product(("empty","demand","unknown"),("empty","demand","unknown"),(0,1)):
        pref,reason=l.demand_preference((left,right),last)
        if "unknown" in (left,right):assert pref is None and reason=="unknown"
    # A possible detection is not validated demand; no camera-only clearance.
    p=perception();v=p.update(0,[PERSON])
    assert v["demand"]=="possible" and v["crossing"]=="unknown"
    assert rp(waiting="unknown",crossing="unknown",oldest_request=0).preference_in_simulation=="abstain"
    for s in LEDGER["studies"]:
        assert not s["candidate_promoted"] and not s["physical_actuation"] and not s["operationally_validated"]
        assert s["research_gate_passed"] is not True
    assert all(not s["applied"] and not s["changes_safety_constraints"] for s in LEDGER["suggestions"])
