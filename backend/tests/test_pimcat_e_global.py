import os
import pytest
from src.benchmarking.pimcat_e_global import Reading,criticity,central_available,arbitrate,network_context,snapshot,case,ensure_version

def test_criticity_and_unknown():
    assert criticity(Reading(10,0,0,10,0),10)==(0,"free")
    assert criticity(Reading(10,10,10,10,0),10)==(1,"critical")
    assert criticity(Reading(10,3,0,10,13.89),10)[1]=="free"
    for tick in (9,16):
        assert criticity(Reading(10,5,3,10,4),tick)==(None,"unknown")
    assert criticity(None,10)==(None,"unknown")
    assert criticity(Reading(10,5,3,10,4),10,False)==(None,"unknown")
    assert snapshot({"edges":{"a":{}}},{"a":Reading(10,5,3,10,4)},10,False)["edges"]["a"]["count"] is None

def test_arbitration_deadlines_capacity_and_fallback():
    a=Reading(100,8,8,10,0);empty=Reading(100,0,0,10,0);full=Reading(100,9,9,10,0)
    local={"A":(a,full),"B":(a,empty)}
    assert arbitrate("global_storage",False,"A",20,100,local,{"A":.5,"B":.5},1,0,{"A":170,"B":0})[0]=="BP"
    assert arbitrate("global_pressure",False,"B",20,100,local,None,0,None,{"A":0,"B":0})==arbitrate("local_pressure",False,"B",20,100,local,None,0,None,{"A":0,"B":0})
    mid={"A":(a,empty)}
    assert arbitrate("global_storage",True,"A",100,100,mid,None,0,None,{"A":0})==("A","P6_rp07")
    assert arbitrate("global_storage",True,"A",100,100,mid,None,1,0,{"A":0})[0]=="P"
    assert not central_available("outage",180) and central_available("outage",300)

@pytest.mark.parametrize("family",["rp07_single","outage"])
def test_real_grid_repeatability(tmp_path,family):
    if os.environ.get("PIMCAT_E_SUMO_REQUIRED")!="1":pytest.skip("pinned SUMO research only")
    api=ensure_version()
    a=case(api,tmp_path/family,family,9100,("local_pressure","global_storage"))
    b=case(api,tmp_path/family,family,9100,("local_pressure","global_storage"))
    assert a==b and a["conflicts_verified"]
    for m in a["metrics"].values():
        assert m["vehicle_scheduled"]==m["vehicle_exited"]+m["vehicle_remaining"]+m["vehicle_uninserted"]
        assert m["pedestrian_scheduled"]==m["pedestrian_exited"]+m["pedestrian_remaining"]+m["pedestrian_uninserted"]
        assert m["conflict_violations"]==m["red_entries"]==m["rp07_empty_interruptions"]==0
    m=a["metrics"]["global_storage"]
    if family=="outage":
        assert m["fallback_ticks"]==180
        assert [s["tick"] for s in m["snapshots"]]==[175,240,305]
        assert all(e["level"]=="unknown" and e["index"] is None for e in m["snapshots"][1]["edges"].values())


def test_graph_context_beyond_local_neighborhood_and_missing_data():
    g={"movements":{"up":{"A":["u","a"]},"here":{"A":["a","b"],"B":["c","d"]},"down":{"A":["b","z"]}}}
    full=Reading(10,10,10,10,0);empty=Reading(10,0,0,10,0)
    obs={k:empty for k in ("u","a","b","c","d","z")}
    obs["u"]=full
    assert network_context(g,obs,"here",10,True)=={"A":.25,"B":0.}
    obs["z"]=full
    assert network_context(g,obs,"here",10,True)=={"A":0.,"B":0.}
    del obs["u"]
    assert network_context(g,obs,"here",10,True) is None
    assert network_context(g,obs,"here",10,False) is None
