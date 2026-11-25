from src.benchmarking import pimcat_i2b_resilience as r

def test_profiles_and_aggregate_gates():
    assert r.PROFILES["ci"][0]==180 and r.PROFILES["dedicated"][0]==86400
    rows=[]
    for t in range(180):
        sources={}
        for k in r.KEYS:
            recent=k=="LAB_CONTROL" or not (30<=t<50 or 100<=t<120)
            sources[k]={"recent":recent,"frames":t,"fps":5 if recent else None,"latency":2 if recent else None,"restarts":0,"age":0}
        rows.append({"t":t,"sources":sources})
    events=[{"unknown_seen":True,"recovery_seconds":10},{"unknown_seen":True,"recovery_seconds":12}]
    s,g=r.summarize(rows,events,"ci",180,True)
    assert all(g.values()) and s["LAB_FAULT"]["recent_share"]==140/180
    assert s["LAB_CONTROL"]["fps"]["p95"]==5
    assert not r.summarize(rows,events,"ci",179,True)[1]["duration"]
    events[0]["recovery_seconds"]=46
    assert not r.summarize(rows,events,"ci",180,True)[1]["fault_recovery"]
    assert not r.summarize(rows[::4],events,"ci",180,True)[1]["sampling_gap"]
