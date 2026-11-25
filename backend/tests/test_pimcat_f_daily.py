import json
from datetime import date,timedelta
import pytest
from fastapi.testclient import TestClient
from src.config import Settings
from src.db import Base
from src.main import create_app
from src.archive.store import fingerprint
from src.reporting.daily import bounds,daily_report,load_day
from src.predictive.store import HistoryIntegrityError
from test_predictive import make_windows

DAY=date(2026,1,1)

def windows():
    start,_=bounds(DAY)
    a=make_windows(1)[0]
    return [a.model_copy(update={"started_at":start+timedelta(seconds=60*i),
      "ended_at":start+timedelta(seconds=60*(i+1)),"start_sequence":1+10*i,"end_sequence":11+10*i,
      "duration_seconds":60,"skipped_frames":int(i==1)}) for i in range(2)]

def test_daily_zero_limited_boundary_and_digest():
    a,b=windows()
    zero=a.model_copy(update={"lines":tuple(l.model_copy(update={"negative_to_positive":0}) for l in a.lines)})
    boundary=b.model_copy(update={"started_at":a.started_at-timedelta(seconds=30),"ended_at":a.started_at+timedelta(seconds=30)})
    r=daily_report("CR_01",DAY,{"CAM_01":[zero,b,boundary]})
    assert r["complete_windows"]==2 and r["boundary_windows_excluded"]==1
    s=next(s for s in r["series"] if s["direction"]=="negative_to_positive")
    assert s["observed"]["passages"]==0 and s["limited"]["passages"]==3
    assert s["coverage_fraction"]==120/86400 and s["unobserved_seconds"]==86280
    assert r["network_total"] is None and not r["aggregation_across_sources"]
    assert all(x["value"] is None for x in r["unavailable_metrics"].values())
    assert fingerprint({k:v for k,v in r.items() if k!="report_sha256"})==r["report_sha256"]
    e=daily_report("CR_01",DAY,{"CAM_01":[]})
    assert e["state"]=="empty" and e["series"]==[] and e["network_total"] is None

def test_reject_mismatch_duplicates_and_overlap():
    a,b=windows()
    with pytest.raises(ValueError):daily_report("CR_02",DAY,{"CAM_01":[a]})
    with pytest.raises(ValueError):daily_report("CR_01",DAY,{"CAM_01":[a,a]})
    with pytest.raises(ValueError):daily_report("CR_01",DAY,{"CAM_01":[a,b.model_copy(update={
        "started_at":a.started_at+timedelta(seconds=30),"ended_at":a.ended_at+timedelta(seconds=30)})]})

def test_separate_source_and_epoch():
    a,b=windows()
    from uuid import uuid4
    r=daily_report("CR_01",DAY,{"CAM_01":[a,b.model_copy(update={"analytics_epoch":uuid4()})],
      "CAM_02":[a.model_copy(update={"source_id":"CAM_02"})]})
    assert len(r["series"])==6 and len(r["sources"])==2

def test_daily_api_and_bounded_scan(tmp_path,monkeypatch):
    s=Settings(app_env="test",archive_enabled=True,database_url=f"sqlite:///{tmp_path/'daily.sqlite'}",
      video_sources_json=json.dumps([{"source_id":"CAM_01","intersection_code":"CR_01","kind":"file","locator":"fixture.avi"}]))
    app=create_app(s)
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        for w in windows():app.state.history.store.save(w)
        url="/api/v1/reporting/intersections/CR_01/daily?day=2026-01-01"
        x=client.get(url);assert x.status_code==200 and x.json()["complete_windows"]==2
        assert x.json()["operational_decision"]=="abstain"
        assert client.get(url.replace("CR_01","UNKNOWN")).status_code==404
        assert client.get(url.replace("2026-01-01","9999-01-01")).status_code==422
        monkeypatch.setattr("src.reporting.daily.MAX_SCAN",1)
        assert client.get(url).status_code==503
