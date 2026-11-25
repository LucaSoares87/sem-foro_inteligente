import os
import pytest
from src.benchmarking import pimcat_d_sumo as d
from src.benchmarking import pimcat_i1b_eta as i1


def test_quantile_calibration_censoring_and_fallback():
    samples=[[100,0,x,7,10,17] for x in range(8,38)]+[[100,0,None,7,10,17]]
    rows=[{"seed":i1.TRAIN[0],"metrics":{"independent":{"eta_samples":samples}}}]
    model=i1.fit(rows)
    assert model["short_clear"]=={"issued":31,"arrived":30,"censored":1,"quantiles":[10,22,34]}
    estimate=i1.predictor(model)
    assert estimate(10,2,100,0)==d.Cohort(10,2,20,32,44,49)
    assert estimate(10,2,100,4)==estimate(10,2,100,0)
    assert i1.predictor({})(10,2,200,0)==d.forecast(10,2,200)
    with pytest.raises(ValueError):estimate(10,2,100,-1)
    with pytest.raises(ValueError):estimate(10,2,float("nan"),0)
    with pytest.raises(AssertionError):i1.fit([{"seed":i1.TEST[0],"metrics":rows[0]["metrics"]}])


@pytest.mark.skipif(os.environ.get("PIMCAT_D_SUMO_REQUIRED")!="1",reason="pinned SUMO research only")
@pytest.mark.parametrize("family",["two_midblock","three_balanced"])
def test_original_parity_and_repeatability(tmp_path,family):
    api=d.ensure_version()
    root=tmp_path/family
    policies=("independent","adaptive_eta_storage")
    a=d.case(api,root,family,i1.TEST[0],policies)
    b=d.case(api,root,family,i1.TEST[0],policies,forecast_fn=lambda t,n,dist,q:d.forecast(t,n,dist),collect_eta=True)
    i1.verify_case(b,policies)
    for p in policies:
        m=dict(b["metrics"][p]);m.pop("eta_samples")
        assert m==a["metrics"][p]
    model={"global":{"issued":40,"arrived":40,"censored":0,"quantiles":[8,20,45]}}
    estimate=i1.predictor(model)
    x=i1.evaluate_case(api,root,family,i1.TEST[0],estimate)
    y=i1.evaluate_case(api,root,family,i1.TEST[0],estimate)
    assert x==y
    i1.verify_case(x,i1.POLICIES)
