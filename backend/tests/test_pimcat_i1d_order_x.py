import os
from src.validation.io import sha256_file
from collections import deque
from itertools import product
import pytest
from src.benchmarking import si11d_sumo as d
from src.benchmarking import si11c_predictive_x as c
from src.benchmarking import pimcat_i1d_order_x as i1


def test_counterfactual_same_green_budget_and_guard():
    for a,b,ar,br in product((0,1,3,10,20),(0,1,3,10,20),(.05,.3),(.05,.3)):
        pair=((0,ar,.5,30),(0,br,.5,30))
        queues=[deque([0]*a),deque([0]*b)]
        base,_=c.select("demand_proportional",pair,queues,60)
        action,reason=i1.select(i1.CANDIDATE,pair,queues,60)
        if reason=="order_minor_first":
            assert action==(1-base[0],c.SERVICE-base[1])
            assert 0<len(queues[action[0]])<len(queues[base[0]])
            assert 12<=action[1]<=40
        else:
            assert action==base
        assert len(c.schedule(action))==c.CYCLE
    pair=((0,.05,.5,30),(0,.3,.5,30))
    assert i1.select(i1.CANDIDATE,pair,[deque(),deque()],0,.64)[0] is None


def test_explicit_order_swap_and_wait_guard(monkeypatch):
    from types import SimpleNamespace
    pair=((0,.05,.5,30),(0,.2,.5,30))
    queues=[deque([0]),deque([0]*5)]
    monkeypatch.setattr(i1.c,"select",lambda *a,**k:((1,32),"proportional"))
    monkeypatch.setattr(i1,"evaluate",lambda *a:SimpleNamespace(origin="synthetic_demo",operational_decision="abstain",physical_actuation=False,operationally_validated=False,preferred_in_simulation="minor_first",minor_clearance_feasible=True,dynamic_x_safe_vehicles=5))
    monkeypatch.setattr(i1,"risk_profile",lambda *a:[{"window":20,"eligible":True}])
    monkeypatch.setattr(i1,"forecast_cost",lambda p,a,ages,s:80 if a[0]==0 else 100)
    assert i1.select(i1.CANDIDATE,pair,queues,60)==((0,20),"order_minor_first")
    assert i1.select(i1.CANDIDATE,pair,queues,160)==((1,32),"order_keep_wait_veto")
    monkeypatch.setattr(i1,"risk_profile",lambda *a:[{"window":20,"eligible":False}])
    assert i1.select(i1.CANDIDATE,pair,queues,60)==((1,32),"order_keep_risk_veto")


def test_canonical_network_hash_ignores_only_nonstructural_xml_metadata(tmp_path):
    a=tmp_path/"a.xml"; b=tmp_path/"b.xml"
    a.write_text('<!-- generated at first time --><net><edge id="a" length="100"/></net>',encoding="utf-8")
    b.write_text('<!-- generated at second time --><net><edge length="100" id="a"/></net>',encoding="utf-8")
    assert sha256_file(a)!=sha256_file(b)
    assert d.canonical_network_sha256(a)==d.canonical_network_sha256(b)
    b.write_text('<!-- generated at second time --><net><edge length="101" id="a"/></net>',encoding="utf-8")
    assert d.canonical_network_sha256(a)!=d.canonical_network_sha256(b)
    b.write_text('<net><edge id="a" length="100"/><connection from="a" to="b"/></net>',encoding="utf-8")
    assert d.canonical_network_sha256(a)!=d.canonical_network_sha256(b)


@pytest.mark.skipif(os.environ.get("SI11D_SUMO_REQUIRED")!="1",reason="pinned offline SUMO only")
@pytest.mark.parametrize("family",["asymmetric","compact_burst"])
def test_original_parity_and_candidate_repeatability(tmp_path,family):
    api=d.ensure_version();root=tmp_path/family
    original=d.case(api,root,family,5000)
    net=root/'network.net.xml'
    assert original['network_sha256']==sha256_file(net)
    # Normalize the legacy result using the actual file before regeneration.
    original['network_sha256']=d.canonical_network_sha256(net)
    hooked=d.case(api,root,family,5000,select_fn=i1.select,canonical_network=True)
    assert original==hooked
    x=d.case(api,root,family,i1.SEEDS[0],i1.POLICIES,select_fn=i1.select,canonical_network=True)
    y=d.case(api,root,family,i1.SEEDS[0],i1.POLICIES,select_fn=i1.select,canonical_network=True)
    assert x==y
    m=x["metrics"][i1.CANDIDATE]
    assert m["scheduled"]==m["inserted"]+m["uninserted"]
    assert m["inserted"]==m["departed_network"]+m["remaining_network"]
    assert not (m["colliding_vehicle_events"] or m["teleports"])
