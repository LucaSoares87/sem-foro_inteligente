import os
import pytest
from src.benchmarking.pimcat_c2_sumo import case, choose, demand, ensure_version, HORIZON


def test_rp07_hold_and_deadline():
    for t in (15,120,300,86400):
        assert choose("predictive_xp","mid","A",t,t,[50,0],[0,0],0,None,(.4,0,0),20)==("A","rp07_hold")
    assert choose("predictive_xp","mid","A",100,100,[40,0],[0,0],1,0,(.4,0,0),20)[0]=="P"
    assert choose("compatible","cross","B",20,20,[2,20],[0,0],1,10,(.2,.3,.1),20)[0]=="BP"


def test_demand_reproducible():
    assert demand("mid_single",7100)==demand("mid_single",7100)
    assert len([r for r in demand("mid_single",7100) if r[1]=="P"])==1
    assert not any(r[1]=="P" for r in demand("mid_empty",7100))


@pytest.mark.parametrize("family",["mid_single","cross_compatible"])
def test_real_repeatability(tmp_path,family):
    if os.environ.get("PIMCAT_C2_SUMO_REQUIRED")!="1":
        pytest.skip("pinned SUMO required only in independent research CI")
    api=ensure_version()
    root=tmp_path/family
    a=case(api,root,family,7100,("actuated","predictive_xp"))
    b=case(api,root,family,7100,("actuated","predictive_xp"))
    assert a==b
    for m in a["metrics"].values():
        assert m["pedestrians_completed"]>0
        assert m["vehicles_scheduled"]==m["vehicles_exited"]+m["vehicles_remaining"]+m["vehicles_uninserted"]
        assert m["pedestrians_scheduled"]==m["pedestrians_exited"]+m["pedestrians_remaining"]+m["pedestrians_uninserted"]
        assert m["conflict_violations"]==m["red_entries"]==0
