import pytest
from src.archive.store import fingerprint
from src.benchmarking.si11_counterfactual import FAMILIES, HORIZON, POLICIES, case, exogenous, run, simulate, snapshot
from src.optimization.engine import evaluate


def test_conservation_and_reproducibility():
    a=case("feasible_near_boundary",100)
    assert a==case("feasible_near_boundary",100)
    assert set(a["metrics"])==set(POLICIES)
    assert len({m["arrivals"] for m in a["metrics"].values()})==1
    for m in a["metrics"].values():
        assert sum(p[0] for p in a["pair"])+m["arrivals"]==m["departed"]+m["remaining"]
        assert m["overflow_exposure_vehicle_seconds"]>=0


def test_empty_system_and_transition():
    pair=((0,0.,1.,24),(0,0.,1.,24))
    arrivals,services=exogenous(pair,100)
    m=simulate(pair,arrivals,services,"A",28)
    assert m["queue_area_vehicle_seconds"]==m["departed"]==m["remaining"]==0
    pair=((60,0.,1.,100),(60,0.,1.,100))
    a,s=exogenous(pair,100)
    m=simulate(pair,a,s,"A",28)
    assert m["departed"]==HORIZON-4 and m["remaining"]==64
    with pytest.raises(ValueError):
        simulate(pair,a,s,"A",60)


def test_confidence_and_synthetic_scope():
    r=evaluate(snapshot(FAMILIES["balanced"],.64))
    assert r.preferred_in_simulation=="abstain" and r.dynamic_x_safe_vehicles is None
    assert r.operational_decision=="abstain" and r.physical_actuation is False


def test_full_study_digest_and_boundaries():
    d=run()
    assert d["overall"]["cases"]==320
    assert d["low_confidence_abstention_verified"]
    assert d["x_validated_for_real_traffic"] is False
    assert d["candidate_promoted"] is False and d["physical_actuation"] is False
    assert d["overall"]["dynamic_queue_area_wins_vs_major"]+d["overall"]["dynamic_queue_area_losses_vs_major"]+d["overall"]["dynamic_queue_area_ties_vs_major"]==320
    body=dict(d)
    h=body.pop("result_sha256")
    assert h==fingerprint(body)
