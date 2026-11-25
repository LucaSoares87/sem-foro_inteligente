import os
import pytest
from src.benchmarking import pimcat_e_global as e
from src.benchmarking import pimcat_i1c_pressure as i1


def test_receiving_space_monotonicity_and_unknown():
    g={"movements":{"up":{"A":["u","a"]},"here":{"A":["a","b"],"B":["c","d"]},"down":{"A":["b","z"]}}}
    def r(count,queue,tick=100):return e.Reading(tick,count,queue,10,0)
    obs={k:r(0,0) for k in ("u","a","b","c","d","z")}
    obs["a"]=r(5,5);obs["u"]=r(8,8)
    def score():
        return e.pressure(obs["a"],obs["b"])+i1.receiving_context(g,obs,"here",100,True)["A"]
    assert score()==pytest.approx(.7)
    obs["b"]=r(7,2)
    assert score()==pytest.approx(-.49)
    obs["z"]=r(10,10)
    assert score()==pytest.approx(-.74)
    assert i1.receiving_context(g,obs,"here",100,False) is None
    obs["z"]=r(0,0,94)
    assert i1.receiving_context(g,obs,"here",100,True) is None
    del obs["z"]
    assert i1.receiving_context(g,obs,"here",100,True) is None


@pytest.mark.skipif(os.environ.get("PIMCAT_E_SUMO_REQUIRED")!="1",reason="pinned SUMO research only")
@pytest.mark.parametrize("family",["rp07_single","outage"])
def test_original_parity_and_repeatability(tmp_path,family):
    api=e.ensure_version();root=tmp_path/family
    a=e.case(api,root,family,9100)
    b=e.case(api,root,family,9100,context_fn=e.network_context)
    assert a==b
    x=i1.evaluate_case(api,root,family,i1.SEEDS[0])
    y=i1.evaluate_case(api,root,family,i1.SEEDS[0])
    assert x==y
    i1.verify_case(x)
