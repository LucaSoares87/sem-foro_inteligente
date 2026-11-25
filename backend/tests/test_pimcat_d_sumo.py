import os
import pytest
from src.benchmarking.pimcat_d_sumo import (forecast,upcoming,capacity_block,choose,demand,case,ensure_version)

def test_aggregate_interval_and_expiry():
    c=forecast(10,7,100)
    assert (c.earliest,c.nominal,c.latest,c.expires)==(18,20,27,32)
    assert upcoming([c],10,4)==4
    assert upcoming([c],33,9)==0
    assert upcoming([c],5,9)==0
    assert upcoming([c],10,9,available=False) is None
    with pytest.raises(ValueError):forecast(0,1,0)

def test_storage_veto_and_rp07():
    assert capacity_block(9,10,0) and not capacity_block(7,10,2)
    assert capacity_block(7,10,2,True)
    for p in ("independent","fixed_offset","adaptive_eta","adaptive_eta_storage"):
        assert choose(p,True,"A",86400,86400,20,0,0,0,0,None,0,False,0)==("A","rp07_hold")
        assert choose(p,True,"A",100,100,20,0,0,0,1,0,0,False,0)[0]=="P"
        assert choose(p,False,"A",20,20,50,1,0,0,1,10,30,True,0)[0]=="BP"
        assert choose(p,False,"A",5,5,50,1,0,0,1,0,30,True,0)[0]=="A"
    assert choose("adaptive_eta",False,"B",20,20,0,2,0,0,0,None,5,False,0)[0]=="A"
    assert choose("independent",False,"B",20,20,0,2,0,0,0,None,5,False,0)[0]=="B"

def test_demand_reproducibility():
    a=demand("two_midblock",8100)
    assert a==demand("two_midblock",8100)
    assert len([r for r in a if r[1]=="P" and r[4]==1])==1

@pytest.mark.parametrize("family",["two_midblock","three_balanced"])
def test_real_network_and_repeatability(tmp_path,family):
    if os.environ.get("PIMCAT_D_SUMO_REQUIRED")!="1":pytest.skip("pinned SUMO research CI only")
    api=ensure_version()
    a=case(api,tmp_path/family,family,8100,("independent","adaptive_eta_storage"))
    b=case(api,tmp_path/family,family,8100,("independent","adaptive_eta_storage"))
    assert a==b
    for m in a["metrics"].values():
        assert m["vehicle_scheduled"]==m["vehicle_exited"]+m["vehicle_remaining"]+m["vehicle_uninserted"]
        assert m["pedestrian_scheduled"]==m["pedestrian_exited"]+m["pedestrian_remaining"]+m["pedestrian_uninserted"]
        assert m["eta_issued"]==m["eta_arrived"]+m["eta_censored"]
        assert m["pedestrian_completed"]>0
        assert m["conflict_violations"]==m["red_entries"]==m["overspeed_samples"]==0
