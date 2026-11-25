import pytest
from src.benchmarking.si10_cpu_profile import parity,p95,read_frames,INDICES,cpu_budget
from src.vision.contracts import Detection

def det(x=.1,label="car",score=.8):
    return Detection(label=label,confidence=score,xyxy=(x,.1,x+.1,.2))

def test_parity_order_and_tolerance():
    a,b=det(),det(.4)
    assert parity([a,b],[b,a])
    assert parity([a],[det(.10001,score=.80001)])
    assert not parity([a],[det(.101)])
    assert not parity([a],[det(label="truck")])
    assert not parity([a],[det(score=.801)])
    assert not parity([a,b],[a,a])
    assert not parity([a],[])
    assert parity([],[])

def test_percentile_and_sample_schedule():
    assert p95(list(range(1,101)))==95
    assert p95([10])==10
    assert len(INDICES)==32 and INDICES[0]==1 and INDICES[-1]==931
    assert cpu_budget()["thread_budget"]>=1

def test_wrong_source_fails_before_decode(tmp_path):
    p=tmp_path/"Bellevue_116th_NE12th__2017-09-11_07-08-32.mp4"
    p.write_bytes(b"not official")
    with pytest.raises(ValueError,match="identity"):
        read_frames("morning_0708",p)
