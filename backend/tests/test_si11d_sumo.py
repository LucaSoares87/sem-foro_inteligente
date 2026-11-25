import os
import pytest

from src.benchmarking.si11_counterfactual import SEEDS as A
from src.benchmarking.si11b_robust_x import SEEDS as B
from src.benchmarking.si11c_predictive_x import SEEDS as C, ACTIONS
from src.benchmarking.si11d_sumo import (
    VERSION, SEEDS, FAMILIES, COHORTS, POLICIES, demand, states,
    build_network, write_routes, ensure_version, trajectory, summarize)


def test_registered_demand():
    assert not set(SEEDS)&(set(A)|set(B)|set(C))
    assert len(FAMILIES)==8 and len(SEEDS)==4 and len(POLICIES)==4
    assert sorted(f for fs in COHORTS.values() for f in fs)==sorted(FAMILIES)
    for f in FAMILIES:
        rates,rows=demand(f,5000)
        assert (rates,rows)==demand(f,5000)
        assert len({v for _,_,v in rows})==len(rows)
        assert all(0<=t<240 and g in (0,1) for t,g,_ in rows)


def test_every_phase_budget_and_permutation():
    for indices in ((0,1),(1,0)):
        for action in ACTIONS:
            s=states(indices,action)
            assert len(s)==60 and s.count("rr")==2
            assert sum("G" in x for x in s)==52
            assert sum("y" in x for x in s)==6
            assert all(x in ("Gr","rG","yr","ry","rr") for x in s)
            w=action[1]
            assert s[w+3]=="rr" and s[-1]=="rr"
    with pytest.raises(ValueError):
        states((0,1),(0,41))


@pytest.mark.skipif(os.environ.get("SI11D_SUMO_REQUIRED")!="1",
                    reason="SUMO is isolated from normal production dependencies")
def test_real_pinned_sumo_smoke(tmp_path):
    api=ensure_version()
    network=build_network(tmp_path,105)
    rates,rows=demand("compact",5000)
    route=tmp_path/"demand.rou.xml"
    write_routes(route,rows)
    a=trajectory(api,network,route,rows,rates,5000,"fixed_alternating")
    b=trajectory(api,network,route,rows,rates,5000,"fixed_alternating")
    assert a==b
    assert a["runtime_version"].split()[-1]==VERSION
    assert a["inserted"]>0 and a["departed_network"]>0
    assert a["scheduled"]==a["inserted"]+a["uninserted"]
    assert a["inserted"]==a["departed_network"]+a["remaining_network"]
    assert sum(a["green_ticks"])==208
    assert a["colliding_vehicle_events"]==a["teleports"]==0
    p=trajectory(api,network,route,rows,rates,5000,"predictive_x")
    assert p["scheduled"]==a["scheduled"]
    assert sum(p["green_ticks"])==208
    assert len(p["plans"])==4


def test_empty_metrics_cannot_pass():
    with pytest.raises(Exception):
        summarize([])
