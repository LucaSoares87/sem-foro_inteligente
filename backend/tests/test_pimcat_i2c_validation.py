import numpy as np
import pytest
from src.benchmarking import pimcat_i2a_calibration as a
from src.benchmarking import pimcat_i2c_temporal as t
from src.benchmarking import pimcat_i2c_reference as r
from src.benchmarking.pimcat_c3_vision import Person

def test_campaign():
    report=t.campaign()
    assert t.verify(report) and report["cases"]==192

def test_window_rejects_invalid_association_and_time():
    H=a.GEOMETRIES[0];cal=a.Calibration([a.project(H,p) for p in a.FIT],a.FIT,[a.project(H,p) for p in a.CHECK],a.CHECK)
    ts=np.arange(5)/10;p=[a.project(H,(3+5*s,6)) for s in ts]
    assert all(v==pytest.approx(5) for v in t.estimates(cal,p,ts,10).values())
    with pytest.raises(ValueError):t.estimates(cal,p,ts,10,False)
    with pytest.raises(ValueError):t.estimates(cal,p,[0,.1,.1,.3,.4],10)
    with pytest.raises(ValueError):t.estimates(cal,p,[0,.01,.2,.3,.4],10)
    p[-1]=a.project(H,(-1,6))
    with pytest.raises(ValueError):t.estimates(cal,p,ts,10)

def test_reference_private_no_fabricated_review(tmp_path):
    raw=b'<annotations><meta><task><name>video_0005</name><size>120</size><original_size><width>100</width><height>100</height></original_size></task></meta><track label="ped"><box frame="0" outside="0" xtl="10" ytl="10" xbr="20" ybr="20"><attribute name="occlusion">none</attribute></box></track><track label="people"><box frame="6" outside="0"/></track></annotations>'
    p=tmp_path/"ref.xml";p.write_bytes(raw)
    ref=r.read_reference(p,"video_0005",r.git_blob_sha(raw))
    assert ref["excluded"]=={6}
    with pytest.raises(ValueError):r.read_reference(p,"video_0005","0"*40)
    selected=set(ref["frames"])-ref["excluded"]
    pred={f:[] for f in selected};pred[0]=[Person((.1,.1,.2,.2),.9)]
    review={f:True for f in selected}
    with pytest.raises(ValueError):r.evaluate_reviewed(ref,pred,review)
    with pytest.raises(ValueError):r.evaluate_reviewed(ref,pred,{},license_reviewed=True,media_verified=True)
    m=r.evaluate_reviewed(ref,pred,review,license_reviewed=True,media_verified=True)
    assert m["tp"]==1 and m["fp"]==m["fn"]==0 and m["c3_independent_precision"].startswith("BLOCKED")
