import os
import pytest
from src.benchmarking.pimcat_h2_gap import gap_bound,gap_available,choose,case,ensure_version

def test_bound_conservative_missing_and_boundary():
    assert gap_bound(10,[],650)==45
    assert gap_bound(10,[13.89],650)==0
    assert gap_bound(10,[],650,False) is None
    assert gap_bound(10,[float("nan")],650) is None

def test_gap_never_overrides_minimum_deadline_or_no_request():
    args=("mid","A",20,20,[0,0],[0,0],1,0,(.1,0,.04),20)
    assert choose("gap_guarded",*args,45)==("P","gap_candidate")
    assert choose("gap_guarded",*args,4)==("A","gap_defer")
    assert choose("gap_guarded",*args,None)[0]=="P"
    assert choose("gap_guarded","mid","A",5,20,[0,0],[0,0],1,0,(.1,0,.04),20,45)[0]=="A"
    assert choose("gap_guarded","mid","A",100,100,[0,0],[0,0],1,0,(.1,0,.04),20,1)[0]=="P"
    assert choose("gap_guarded","mid","A",100,100,[0,0],[0,0],0,None,(.1,0,.04),20,45)[0]=="A"
    assert not gap_available("mid_slow",180)

@pytest.mark.skipif(os.environ.get("PIMCAT_H2_SUMO_REQUIRED")!="1",reason="pinned SUMO study only")
@pytest.mark.parametrize("family",["mid_sparse","cross_deadlines"])
def test_actual_sumo_and_repeatability(tmp_path,family):
    api=ensure_version()
    a=case(api,tmp_path/family,family,10100,("compatible","gap_guarded"))
    b=case(api,tmp_path/family,family,10100,("compatible","gap_guarded"))
    assert a==b
    for m in a["metrics"].values():
        assert m["vehicles_scheduled"]==m["vehicles_exited"]+m["vehicles_remaining"]+m["vehicles_uninserted"]
        assert m["pedestrians_scheduled"]==m["pedestrians_exited"]+m["pedestrians_remaining"]+m["pedestrians_uninserted"]
        assert m["red_entries"]==m["conflict_violations"]==m["colliding_vehicle_events"]==m["overspeed_samples"]==0
        assert m["protected_episodes_zero_new_A_stops"]<=m["protected_episodes_complete"]
