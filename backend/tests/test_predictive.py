import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from src.analytics.contracts import TrafficSnapshot,RegionMetric,LineMetric
from src.predictive.aggregation import WindowAccumulator
from src.predictive.forecast import estimate
from src.predictive.store import HistoryStore,HistoryIntegrityError
from src.predictive.service import HistoryService
from src.config import Settings
from src.db import Base,TrafficWindowRecord
from src.main import create_app

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
EPOCH,SESSION,TRACKING=uuid4(),uuid4(),uuid4()

def snapshot(n,at=None,count=0,visible=2,**kw):
    values=dict(source_id="CAM_01",intersection_code="CR_01",session_id=SESSION,
        tracking_epoch=TRACKING,analytics_epoch=EPOCH,geometry_sha256="a"*64,model_sha256="b"*64,
        purpose="validation_only",frame_sequence=n+1,received_at=BASE+timedelta(seconds=n if at is None else at),
        window_started_at=BASE,observed_batches=n+1,skipped_frames=0,discontinuities=0,
        tentative_visible=0,lost_private=0,quality="experimental",
        regions=(RegionMetric(region_id="R",confirmed_visible=visible,image_coverage_pct=20),),
        lines=(LineMetric(line_id="L",negative_to_positive=count,positive_to_negative=0),))
    values.update(kw)
    return TrafficSnapshot(**values)

def make_windows(n=12,variable=False):
    acc=WindowAccumulator()
    results=[]
    count=0
    for i in range(n*60+1):
        if i and i%60==0:
            count+=1+(i//60)%4 if variable else 3
        w=acc.consume(snapshot(i,count=count))
        if w is not None:
            results.append(w)
    return results

def test_windows_are_nonoverlap_and_time_weighted():
    a=WindowAccumulator()
    assert a.consume(snapshot(0,count=7,visible=0)) is None
    for n in range(1,60):
        assert a.consume(snapshot(n,count=8,visible=2)) is None
    w=a.consume(snapshot(60,count=10,visible=4))
    assert w.duration_seconds==60
    assert w.lines[0].negative_to_positive==3
    assert w.regions[0].peak_visible==4
    assert w.regions[0].mean_visible==pytest.approx(2)
    assert w.regions[0].mean_image_coverage_pct==pytest.approx(20)
    assert w.sampled_intervals==60
    assert w.start_sequence==1 and w.end_sequence==61
    assert w.operationally_validated is False
    next_windows=make_windows(2)
    assert next_windows[0].end_sequence==next_windows[1].start_sequence
    assert next_windows[0].ended_at==next_windows[1].started_at
    assert [x.lines[0].negative_to_positive for x in next_windows]==[3,3]

def test_gaps_resets_and_counter_regression():
    a=WindowAccumulator()
    a.consume(snapshot(0,count=10))
    a.consume(snapshot(1,count=15))
    a.consume(snapshot(2,count=12))
    assert a.start.frame_sequence==3
    a.consume(snapshot(3,at=10,count=12))
    assert a.start.frame_sequence==4
    a.consume(snapshot(4,at=11,count=13,discontinuities=1))
    assert a.start.frame_sequence==5
    a.consume(snapshot(5,at=12,count=14,analytics_epoch=uuid4()))
    assert a.start.frame_sequence==6
    a.consume(snapshot(6,at=13,regions=(),count=0))
    a.consume(snapshot(7,at=14,regions=(),lines=()))
    assert a.start.frame_sequence==8
    a.consume(snapshot(8,at=15,regions=(RegionMetric(region_id="Z",confirmed_visible=1,image_coverage_pct=0),),lines=()))
    assert a.start.frame_sequence==9

def test_limited_interval_and_no_fabricated_zero():
    a=WindowAccumulator()
    w=None
    for n in range(61):
        w=a.consume(snapshot(n,count=3,skipped_frames=int(n>=30),tentative_visible=int(n==40)))
    assert w.skipped_frames==1
    assert w.limited_intervals>=2
    assert estimate([w]*12,"L","negative_to_positive")["state"]=="insufficient_data"

def test_backtesting_and_abstention():
    ws=make_windows()
    assert len(ws)==12
    r=estimate(ws,"L","negative_to_positive")
    assert r["state"]=="experimental"
    assert r["estimate"]==3
    assert r["mae_mean_last_3"]==0 and r["mae_persistence"]==0
    assert r["empirical_error_band"]==[3,3]
    assert r["backtest_samples"]==9
    assert r["operationally_validated"] is False
    assert estimate(ws[:11],"L","negative_to_positive")["state"]=="insufficient_data"
    assert estimate(ws,"UNKNOWN","negative_to_positive")["state"]=="insufficient_data"
    assert estimate(ws,"L","positive_to_negative")["estimate"]==0
    assert estimate(ws[:-1]+[ws[-1].model_copy(update={"start_sequence":9999})],"L","negative_to_positive")["state"]=="insufficient_data"
    with pytest.raises(ValueError):
        estimate(ws,"L","invalid")
    changed=make_windows(variable=True)
    assert estimate(changed,"L","negative_to_positive")["backtest_samples"]==9
    rising=[w.model_copy(update={"lines":(LineMetric(line_id="L",negative_to_positive=i,positive_to_negative=0),)}) for i,w in enumerate(ws)]
    assert estimate(rising,"L","negative_to_positive")["method"]=="persistence"

def test_store_idempotency_and_integrity(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'history.db'}")
    Base.metadata.create_all(engine)
    store=HistoryStore(engine)
    ws=make_windows(2)
    for w in ws:
        store.save(w)
        store.save(w)
    page=store.page("CAM_01",0,1)
    assert page["has_more"] and page["items"][0]["window"]==ws[0]
    assert store.page("CAM_01",page["next_cursor"],1)["items"][0]["window"]==ws[1]
    assert store.recent("CAM_01",EPOCH)==ws
    with pytest.raises(HistoryIntegrityError):
        store.save(ws[0].model_copy(update={"limited_intervals":1}))
    with Session(engine) as session:
        row=session.scalar(select(TrafficWindowRecord))
        row.digest="0"*64
        session.commit()
    with pytest.raises(HistoryIntegrityError):
        store.page("CAM_01",0,2)
    engine.dispose()

def test_async_writer_failure_and_capacity():
    class Store:
        def save(self,w):
            raise RuntimeError("private")
    async def run():
        service=HistoryService(Store(),True)
        service.start()
        for n in range(34*60+1):
            service.consume(snapshot(n))
        assert service.queue.qsize()==32 and service.dropped==2
        await service.stop()
        assert service.failed==32
        assert service.status()["state"]=="degraded"
        assert service.queue.empty()
    asyncio.run(run())

def test_history_api_and_live_forecast(tmp_path):
    settings=Settings(app_env="test",archive_enabled=True,database_url=f"sqlite:///{tmp_path/'db.sqlite'}")
    app=create_app(settings)
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.engine)
        windows=make_windows()
        for w in windows:
            app.state.history.store.save(w)
        assert client.get("/api/v1/predictive/status").json()["state"]=="available"
        assert client.get("/api/v1/predictive/sources/CAM_01/history?limit=1").json()["has_more"]
        url="/api/v1/predictive/sources/CAM_01/forecast?line_id=L"
        assert client.get(url).json()["reason"]=="no_current_live_snapshot"
        current=snapshot(720,count=36)
        app.state.analytics.latest=lambda source:current
        app.state.video.sessions["CAM_01"]=SimpleNamespace(state="running",stop=lambda:None)
        try:
            assert client.get(url).json()["estimate"]==3
            assert client.get("/api/v1/predictive/sources/CAM_01/forecast?line_id=MISSING").status_code==404
        finally:
            app.state.video.sessions.pop("CAM_01")
        assert client.get("/health/live").status_code==200

def test_disabled_history(tmp_path):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'db.sqlite'}")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/predictive/status").json()["state"]=="disabled"
        assert client.get("/api/v1/predictive/sources/CAM_01/history").status_code==503
