from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from src.analytics.contracts import SourceGeometry,CountingLine,Region,load_geometry
from src.analytics.engine import TrafficEngine
from src.analytics.geometry import union_area,image_coverage,crosses_segment,side,foot,contains
from src.analytics.service import AnalyticsService
from src.tracking.contracts import TrackBatch,TrackObservation
from src.config import Settings
from src.main import create_app

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
SESSION=uuid4()
EPOCH=uuid4()
GEOMETRY={"source_id":"CAM_01","intersection_code":"CR_01",
          "regions":[{"region_id":"R","xyxy":[0,0,1,1]}],
          "lines":[{"line_id":"L","start":[.5,.2],"end":[.5,.8]}]}

def track(x=.3,y=.5,idx=1,state="confirmed",label="car"):
    return TrackObservation(track_id=idx,label=label,state=state,confidence=.9,
        xyxy=(x-.05,y-.1,x+.05,y),hits=2 if state=="confirmed" else 1)

def batch(n,tracks=(),at=None,session=SESSION,epoch=EPOCH,source="CAM_01"):
    return TrackBatch(source_id=source,intersection_code="CR_01",session_id=session,
        tracking_epoch=epoch,frame_sequence=n,received_at=BASE+timedelta(seconds=n*.1 if at is None else at),
        model_sha256="a"*64,purpose="validation_only",tracking_ms=1,skipped_frames=0,
        lost_private=0,tracks=tuple(tracks))

def config():
    return SourceGeometry.model_validate(GEOMETRY)

def test_geometry_and_union():
    assert union_area([])==0
    assert union_area([(0,0,.5,.5),(.25,.25,.75,.75)])==pytest.approx(.4375)
    assert union_area([(0,0,.5,.2),(0,.4,.5,.6)])==pytest.approx(.2)
    assert image_coverage((0,0,.5,.5),[(.25,.25,.75,.75),(0,.6,1,1)])==pytest.approx(25)
    assert contains((0,0,1,1),foot((0,0,1,1)))
    line=config().lines[0]
    assert side(line,(.3,.5))==1
    assert side(line,(.5,.5))==0
    assert side(line,(.7,.5))==-1
    assert crosses_segment(line,(.3,.5),(.7,.5))
    assert not crosses_segment(line,(.3,.1),(.7,.1))
    assert not crosses_segment(line,(.1,.5),(.3,.5))

def test_passage_directions_hysteresis_and_no_stationary_repeats():
    engine=TrafficEngine(config())
    first=engine.consume(batch(1,[track()]))
    assert first.quality=="initializing"
    assert first.regions[0].confirmed_visible==1
    assert first.regions[0].image_coverage_pct==pytest.approx(1)
    engine.consume(batch(2,[track(.49)]))
    crossed=engine.consume(batch(3,[track(.65)]))
    assert crossed.lines[0].positive_to_negative==1
    assert crossed.lines[0].negative_to_positive==0
    assert crossed.quality=="experimental"
    engine.consume(batch(4,[track(.65)]))
    engine.consume(batch(5,[track(.51)]))
    back=engine.consume(batch(6,[track(.3)]))
    assert back.lines[0].positive_to_negative==1
    assert back.lines[0].negative_to_positive==1
    assert back.operationally_validated is False
    assert back.observed_batches==6
    assert first.analytics_epoch==back.analytics_epoch

def test_outside_line_missing_track_and_tentative_not_counted():
    e=TrafficEngine(config())
    e.consume(batch(1,[track(.3,.15)]))
    assert e.consume(batch(2,[track(.7,.15)])).lines[0].positive_to_negative==0
    e.consume(batch(3,[track(.3)]))
    e.consume(batch(4))
    a=e.consume(batch(5,[track(.7)]))
    assert a.lines[0].positive_to_negative==0
    b=e.consume(batch(6,[track(.3,state="tentative")]))
    assert b.tentative_visible==1 and b.regions[0].confirmed_visible==0
    assert b.quality=="limited_sampling"

def test_gap_and_session_reset():
    e=TrafficEngine(config())
    e.consume(batch(1,[track(.3)]))
    g=e.consume(batch(10,[track(.7)]))
    assert g.discontinuities==1 and g.skipped_frames==8
    assert g.lines[0].positive_to_negative==0
    assert g.quality=="limited_sampling"
    e.consume(batch(11,[track(.3)]))
    reset=e.consume(batch(1,[track(.7)],session=uuid4()))
    assert reset.analytics_epoch!=g.analytics_epoch
    assert reset.observed_batches==1 and reset.skipped_frames==0
    assert reset.lines[0].negative_to_positive==0
    with pytest.raises(ValueError,match="out-of-order"):
        e.consume(batch(1,[track(.7)],session=reset.session_id))
    with pytest.raises(ValueError,match="source mismatch"):
        e.consume(batch(2,source="CAM_02"))
    with pytest.raises(ValueError,match="duplicate"):
        e.consume(batch(2,[track(),track()],session=reset.session_id))

def test_expired_anchor_and_clock_regression():
    e=TrafficEngine(config())
    e.consume(batch(1,[track(.3)]))
    for n in range(2,8):
        e.consume(batch(n,[track(.5)]))
    result=e.consume(batch(8,[track(.7)]))
    assert result.lines[0].positive_to_negative==0
    result=e.consume(batch(9,[track(.3)],at=.1))
    assert result.discontinuities==1
    assert result.lines[0].negative_to_positive==0

def test_registry_validation():
    assert load_geometry(json.dumps([GEOMETRY]),{"CAM_01":"CR_01"})["CAM_01"]==config()
    for data in ["bad","{}",json.dumps([GEOMETRY,GEOMETRY]),json.dumps([GEOMETRY]*9)]:
        with pytest.raises(ValueError,match="invalid traffic geometry"):
            load_geometry(data,{"CAM_01":"CR_01"})
    with pytest.raises(ValueError):
        load_geometry(json.dumps([GEOMETRY]),{})
    with pytest.raises(ValueError):
        Region(region_id="R",xyxy=(.5,0,.2,1))
    with pytest.raises(ValueError):
        CountingLine(line_id="L",start=(0,0),end=(0,0))
    with pytest.raises(ValueError):
        CountingLine(line_id="L",start=(-.1,0),end=(1,1))
    with pytest.raises(ValueError):
        SourceGeometry(source_id="CAM_01",intersection_code="CR_01")

def test_service_isolation_and_invalid_config(tmp_path):
    current={"CAM_01":batch(1,[track()])}
    tracking=SimpleNamespace(latest=current.get,
        vision=SimpleNamespace(video=SimpleNamespace(sessions={"CAM_01":SimpleNamespace(state="running")})))
    service=AnalyticsService(tracking,{"CAM_01":config()})
    assert service.status()["state"]=="idle"
    service.consume(current["CAM_01"])
    assert service.status()["state"]=="available"
    service.consume(current["CAM_01"])
    assert service.status()["state"]=="degraded"
    assert service.latest("CAM_01") is None
    current["CAM_01"]=batch(2,[track()])
    service.consume(current["CAM_01"])
    assert service.status()["state"]=="available"
    current["CAM_01"]=batch(3)
    assert service.latest("CAM_01") is None
    service.clear()
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'db.sqlite'}",traffic_geometry_json="invalid")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code==200
        assert client.get("/api/v1/analytics/status").json()["error_code"]=="geometry_config_invalid"
        assert client.get("/api/v1/analytics/sources/CAM_01/latest").status_code==404
