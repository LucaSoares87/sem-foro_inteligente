from src.benchmarking import field_integrated_lab as d

def fixture():
    rows=[]
    for t in range(100):
        recent=t<25 or t>=50;session="a" if t<50 else "b"
        count=min(t,20)*5+max(0,t-49)*5
        rows.append(dict(t=float(t),recent=recent,session=session,analytics_session=session if recent else None,
                         capture=count,vision=count,tracking=count,analytics=count,decode_receive_ms=.5 if recent else None))
    return rows

def summary(rows):
    return d.summarize(rows,dict(off=20.,on=40.),100.,True,None,dict(tracking=0,analytics=0),dict(vision=350,tracking=350,analytics=350))

def test_recovery_and_denominators():
    r=summary(fixture());assert all(r["checks"].values())
    assert r["recovery_seconds"]==10 and r["fps"]["capture"]==350/99 and r["unknown_observed"]

def test_missing_loss_and_new_session_fail():
    rows=fixture()
    for r in rows:r["recent"]=True
    assert not summary(rows)["checks"]["recovery"]
    rows=fixture()
    for r in rows:r["session"]="a";r["analytics_session"]="a"
    assert not summary(rows)["checks"]["recovery"]

def test_short_or_inconsistent_fails():
    r=d.summarize(fixture()[:50],dict(off=20.,on=40.),50.,False,"TimeoutError",dict(tracking=1),dict(vision=10,tracking=9,analytics=9))
    for k in ("duration","coverage","cleanup","no_error","no_stage_failures","stage_conservation"):assert not r["checks"][k]

def test_missing_boundary_samples_and_failures_rejected():
    rows=fixture()
    for r in rows:r["t"]+=4
    assert not summary(rows)["checks"]["sampling_gap"]
    assert not d.summarize(fixture(),dict(off=20.,on=40.),110.,True,None,dict(tracking=0,analytics=0),dict(vision=350,tracking=350,analytics=350))["checks"]["sampling_gap"]
    assert not d.summarize(fixture(),dict(off=20.,on=40.),100.,True,None,{},dict(vision=350,tracking=350,analytics=350))["checks"]["no_stage_failures"]

def test_worker_resources_reset_unknown_and_missing():
    assert d.worker_resources([])==(None,None)
    assert d.worker_resources([dict(cpu_seconds=2.,rss_kib=100),dict(cpu_seconds=1.,rss_kib=200)])==(None,200)
    assert d.worker_resources([dict(cpu_seconds=1.,rss_kib=100),dict(cpu_seconds=2.,rss_kib=200)])==(1.,200)
