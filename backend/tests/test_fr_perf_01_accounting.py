import pytest
from src.benchmarking.fr_perf_01_accounting import trial_order, summarize_paced, coverage, OFFERED

def data():
    offers={k:k/5 for k in range(OFFERED)}
    completed={k:dict(done=t+.1,received=t,inference_ms=80) for k,t in offers.items()}
    return offers,completed

def test_balanced_and_budget():
    assert trial_order(4)==[[1,2,4],[2,4,1],[4,1,2]]
    assert trial_order(2)==[[1,2],[2,1],[1,2]]
    assert trial_order(1)==[[1],[1],[1]]
    with pytest.raises(ValueError):trial_order(0)

def test_complete():
    o,c=data()
    r=summarize_paced(o,c,[],[],[])
    assert r["capacity_gate"] and r["effective_fps"]==5

def test_loss_not_hidden():
    o,c=data()
    lost=list(range(26))
    for k in lost:del c[k]
    r=summarize_paced(o,c,lost,[],[])
    assert not r["capacity_gate"] and r["completed_within_window"]==474
    with pytest.raises(ValueError):summarize_paced(o,c,lost+[26],[],[])
    with pytest.raises(ValueError):summarize_paced(o,c,[],[],[])

def test_late_and_invalid():
    o,c=data()
    for k in c:c[k]["done"]+=.2
    assert not summarize_paced(o,c,[],[],[])["capacity_gate"]
    c[0]["received"]=1
    with pytest.raises(ValueError):summarize_paced(o,c,[],[],[])

def test_missing_and_boundary():
    o,c=data();del o[0]
    with pytest.raises(ValueError):summarize_paced(o,c,[],[],[])
    assert coverage(list(range(100)),100)
    assert not coverage(list(range(4,100)),100)
    assert not coverage(list(range(100)),104)
    assert not coverage([0]*100,100)
