from collections import deque
import pytest

from src.benchmarking.si11_counterfactual import SEEDS as SEEDS_A
from src.benchmarking.si11b_robust_x import SEEDS as SEEDS_B
from src.benchmarking.si11c_predictive_x import (
    ACTIONS,CYCLE,CYCLES,SERVICE,SEEDS,REPLICATION,NOVEL_SHIFT,POLICIES,
    schedule,streams,admissible,predictive,select,case,summarize)
from src.benchmarking.si11b_robust_x import risk_profile


def test_equal_service_and_transitions_for_every_action():
    for action in ACTIONS:
        s=schedule(action)
        assert len(s)==CYCLE and s.count(None)==8
        assert s.count(0)+s.count(1)==SERVICE
        assert min(s.count(0),s.count(1))>=12
    with pytest.raises(ValueError):
        schedule((0,41))


def test_robust_minor_constraint_and_abstention():
    p=REPLICATION["feasible_near_boundary"]
    allowed=admissible(p,1,True)
    assert all((a[0]==1 or any(r["eligible"] and r["window"]==a[1]
               for r in risk_profile(p[0],p[1]))) for a in allowed)
    assert all((1,w) in allowed for w in (12,20,26,32,40))
    q=[deque([0]*x[0]) for x in p]
    assert select("predictive_x",p,q,0,.64)==(None,"low_confidence_abstain")
    a=predictive(p,1,True)
    assert a is None or a in allowed


def test_common_workload_and_deterministic_study():
    p=NOVEL_SHIFT["service_outage"]
    a=case("novel_shift","service_outage",p,3000)
    assert a==case("novel_shift","service_outage",p,3000)
    assert set(a["metrics"])==set(POLICIES)
    assert len({v["arrivals"] for v in a["metrics"].values()})==1
    for v in a["metrics"].values():
        assert sum(x[0] for x in a["pair"])+v["arrivals"]==v["departed"]+v["remaining"]
        assert sum(v["service_opportunity_ticks"])==SERVICE*CYCLES
        assert min(v["service_opportunity_ticks"])>=12*CYCLES
        assert len(v["plans"])==CYCLES
    summary=summarize([a])
    assert summary["cases"]==1
    assert set(summary["gates"])=={"original_x","robust_x","demand_proportional","fixed_alternating"}


def test_disjoint_seeds_and_empty_case():
    assert not set(SEEDS)&(set(SEEDS_A)|set(SEEDS_B))
    assert not set(REPLICATION)&set(NOVEL_SHIFT)
    a=case("novel_shift","empty_shift",NOVEL_SHIFT["empty_shift"],3001)
    assert all(v["departed"]==v["remaining"]==v["queue_area_vehicle_seconds"]==0 for v in a["metrics"].values())
