import copy
from src.benchmarking import pimcat_i2b_resilience as r

def samples():
    rows=[]
    for t in range(180):
        sources={}
        for k in r.KEYS:
            recent=k=="LAB_CONTROL" or not (30<=t<50 or 100<=t<120)
            sources[k]={"recent":recent,"frames":t,"fps":5 if recent else None,"latency":2 if recent else None,"restarts":0,"age":0}
        rows.append({"t":t,"sources":sources})
    return rows

def events(rows):
    return r.fault_evidence(rows,[{"off":30,"on":50},{"off":100,"on":120}])

def test_profiles_and_aggregate_gates():
    assert r.PROFILES["ci"][0]==180 and r.PROFILES["dedicated"][0]==86400
    rows=samples(); ev=events(rows)
    s,g=r.summarize(rows,ev,"ci",180,True)
    assert all(g.values()) and s["LAB_FAULT"]["recent_share"]==140/180
    assert s["LAB_CONTROL"]["fps"]["p95"]==5
    assert not r.summarize(rows,ev,"ci",179,True)[1]["duration"]
    assert not r.summarize(rows[::4],events(rows[::4]),"ci",180,True)[1]["sampling_gap"]

def test_buffered_frames_cannot_count_as_recovery_without_observed_loss():
    rows=samples()
    for row in rows:
        if 30<=row["t"]<50:
            row["sources"]["LAB_FAULT"]["recent"]=True
    ev=events(rows)
    assert ev[0]["unknown_seen"] is False and ev[0]["recovery_seconds"] is None
    assert not r.summarize(rows,ev,"ci",180,True)[1]["fault_recovery"]
    forged=copy.deepcopy(ev);forged[0]["unknown_seen"]=True;forged[0]["recovery_seconds"]=0
    assert not r.summarize(rows,forged,"ci",180,True)[1]["fault_recovery"]

def test_recovery_requires_new_frames_and_keeps_45_second_limit():
    rows=samples()
    for row in rows:
        if 50<=row["t"]<96:
            row["sources"]["LAB_FAULT"]["recent"]=False
    ev=events(rows)
    assert ev[0]["unknown_at"]==30 and ev[0]["recovery_seconds"]==46
    assert not r.summarize(rows,ev,"ci",180,True)[1]["fault_recovery"]
    rows=samples()
    for row in rows:
        if 50<=row["t"]<55:
            row["sources"]["LAB_FAULT"]["frames"]=49
    ev=events(rows)
    assert ev[0]["recovery_at"]==55 and ev[0]["recovery_seconds"]==5
    assert r.summarize(rows,ev,"ci",180,True)[1]["fault_recovery"]
