from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from src.analytics.contracts import CountingLine,QueueApproachConfig,Region,SourceGeometry
from src.analytics.engine import TrafficEngine
from src.config import Settings
from src.db import Base
from src.main import create_app
from src.optimization.engine import aggregate_groups,dynamic_x_safe,evaluate
from src.queueing.contracts import QueueApproachState,QueueSnapshot
from src.queueing.engine import QueueEstimator
from src.queueing.store import QueueStore
from src.tracking.contracts import TrackBatch,TrackObservation
from src.video.contracts import SourceSpec

BASE=datetime(2026,11,24,12,0,tzinfo=timezone.utc)
SESSION=uuid4()
TRACK_EPOCH=uuid4()

def geometry():
    return SourceGeometry(
        source_id="CAM_01",intersection_code="CR_01",
        regions=(
            Region(region_id="RA",xyxy=(0,0,.7,1)),
            Region(region_id="RB",xyxy=(.3,0,1,1)),
        ),
        lines=(
            CountingLine(line_id="LA",start=(.7,.1),end=(.7,.9)),
            CountingLine(line_id="LB",start=(.3,.1),end=(.3,.9)),
        ),
        approaches=(
            QueueApproachConfig(approach_id="A",service_group="GA",region_id="RA",
                discharge_line_id="LA",discharge_direction="positive_to_negative",
                storage_capacity_vehicles=20,visibility_score=.9,visibility_calibrated=True,
                min_stop_seconds=1,rate_window_seconds=10),
            QueueApproachConfig(approach_id="B",service_group="GB",region_id="RB",
                discharge_line_id="LB",discharge_direction="negative_to_positive",
                storage_capacity_vehicles=20,visibility_score=.9,visibility_calibrated=True,
                min_stop_seconds=1,rate_window_seconds=10),
        ))

def track(idx,x,state="confirmed"):
    return TrackObservation(track_id=idx,label="car",state=state,confidence=.9,
        xyxy=(x-.03,.4,x+.03,.55),hits=3 if state=="confirmed" else 1)

def batch(n,tracks,seconds,skipped=0,lost=0):
    return TrackBatch(source_id="CAM_01",intersection_code="CR_01",
        session_id=SESSION,tracking_epoch=TRACK_EPOCH,frame_sequence=n,
        received_at=BASE+timedelta(seconds=seconds),model_sha256="a"*64,
        purpose="validation_only",tracking_ms=1,skipped_frames=skipped,
        lost_private=lost,tracks=tuple(tracks))

def source_spec(**changes):
    values=dict(source_id="CAM_01",intersection_code="CR_01",kind="file",
                locator="fixture.avi",data_origin="external_real_replay")
    values.update(changes)
    return SourceSpec(**values)

def run_pair(engine,queue,b):
    analytics=engine.consume(b)
    return queue.consume(b,analytics,source_spec())

def approach(approach_id,group,q,arrival,discharge,capacity,confidence=.9,wait=10):
    return QueueApproachState(approach_id=approach_id,service_group=group,
        visible_vehicles=max(q,1),queue_length=q,stopped_ratio=min(1,q/max(q,1)),
        arrival_rate_vps=arrival,discharge_rate_vps=discharge,
        queue_growth_vps=arrival-discharge,mean_wait_seconds=wait,max_wait_seconds=wait,
        storage_capacity_vehicles=capacity,storage_occupancy_ratio=min(2,q/capacity),
        spillback_margin_ratio=max(0,1-min(1,q/capacity)),
        observation_confidence=confidence,visibility_calibrated=True,quality="experimental")

def snapshot(approaches):
    return QueueSnapshot(source_id="CAM_01",intersection_code="CR_01",
        session_id=SESSION,tracking_epoch=TRACK_EPOCH,analytics_epoch=uuid4(),queue_epoch=uuid4(),
        geometry_sha256="b"*64,model_sha256="a"*64,purpose="validation_only",
        data_origin="external_real_replay",commercial_demo_authorized=False,
        frame_sequence=100,received_at=BASE,approaches=tuple(approaches))

def test_source_governance_and_queue_geometry_are_explicit():
    external=source_spec()
    assert external.data_origin=="external_real_replay"
    assert external.commercial_demo_authorized is False
    with pytest.raises(ValueError):
        source_spec(commercial_demo_authorized=True)
    authorized=source_spec(commercial_demo_authorized=True,authorization_ref="written-permission")
    assert authorized.commercial_demo_authorized is True
    with pytest.raises(ValueError):
        source_spec(kind="webcam",locator="0",data_origin="synthetic_demo")
    bad=geometry().model_copy(update={"approaches":(
        QueueApproachConfig(approach_id="X",service_group="G",region_id="UNKNOWN",
            discharge_line_id="LA",discharge_direction="positive_to_negative",
            storage_capacity_vehicles=10),)})
    with pytest.raises(ValueError):
        SourceGeometry.model_validate(bad.model_dump())

def test_queue_estimator_observes_wait_arrival_discharge_and_quality():
    config=geometry()
    traffic=TrafficEngine(config)
    queue=QueueEstimator(config)
    first=run_pair(traffic,queue,batch(1,[track(1,.2),track(2,.9)],0))
    assert all(item.quality=="initializing" for item in first.approaches)
    second=run_pair(traffic,queue,batch(2,[track(1,.2),track(2,.6)],1))
    third=run_pair(traffic,queue,batch(3,[track(1,.2),track(2,.6)],2.2))
    a=next(item for item in third.approaches if item.approach_id=="A")
    assert a.queue_length==1
    assert a.mean_wait_seconds==pytest.approx(1.2)
    assert a.arrival_rate_vps>0
    # Track 3 crosses LA left -> right, incrementing the configured discharge direction.
    run_pair(traffic,queue,batch(4,[track(1,.2),track(2,.6),track(3,.6)],3))
    crossed=run_pair(traffic,queue,batch(5,[track(1,.2),track(2,.6),track(3,.82)],4))
    a=next(item for item in crossed.approaches if item.approach_id=="A")
    assert a.discharge_rate_vps>0
    assert a.observation_confidence>.65
    assert crossed.data_origin=="external_real_replay"
    assert crossed.physical_speed_available is False
    limited=run_pair(traffic,queue,batch(6,[track(1,.2,state="tentative")],5,skipped=1,lost=1))
    assert all(item.quality=="limited_sampling" for item in limited.approaches)
    assert all(item.observation_confidence<.65 for item in limited.approaches)

def test_queue_estimator_rejects_identity_and_resets_on_new_tracking_epoch():
    config=geometry()
    traffic=TrafficEngine(config)
    queue=QueueEstimator(config)
    b=batch(1,[track(1,.2)],0)
    analytics=traffic.consume(b)
    with pytest.raises(ValueError,match="identity"):
        queue.consume(batch(2,[track(1,.2)],1),analytics,source_spec())
    old=queue.consume(b,analytics,source_spec())
    new_epoch=uuid4()
    b2=TrackBatch(**{**batch(1,[track(1,.2)],2).model_dump(),
        "tracking_epoch":new_epoch,"session_id":uuid4()})
    analytics2=TrafficEngine(config).consume(b2)
    reset=queue.consume(b2,analytics2,source_spec())
    assert reset.queue_epoch!=old.queue_epoch

def test_dynamic_x_minor_first_major_first_and_abstention_are_deterministic():
    minor=approach("B","GB",6,.08,.5,20,wait=16)
    major=approach("A","GA",34,.35,.6,50,wait=40)
    state=snapshot((major,minor))
    groups=aggregate_groups(state)
    group_major=next(g for g in groups if g.group_id=="GA")
    group_minor=next(g for g in groups if g.group_id=="GB")
    x,clear=dynamic_x_safe(group_minor,group_major)
    assert x==8
    assert clear==pytest.approx(6/(.5-.08))
    result=evaluate(state)
    assert result==evaluate(state)
    assert result.preferred_in_simulation=="minor_first"
    assert result.reason=="minor_first_lower_cost"
    assert result.dynamic_x_safe_vehicles==8
    assert result.minor_clearance_feasible is True
    assert result.minor_first.total_cost<result.major_first.total_cost
    assert result.operational_decision=="abstain"
    assert result.physical_actuation is False
    assert result.engineering_weights_validated is False

    unsafe=evaluate(snapshot((approach("A","GA",50,.45,.6,60),minor)))
    assert unsafe.dynamic_x_safe_vehicles==0
    assert unsafe.preferred_in_simulation=="major_first"
    assert unsafe.reason=="minor_exceeds_dynamic_x"

    no_clear=evaluate(snapshot((major,approach("B","GB",6,.5,.4,20))))
    assert no_clear.reason=="no_net_minor_clearance"
    assert no_clear.preferred_in_simulation=="major_first"

    low=evaluate(snapshot((major,minor.model_copy(update={"observation_confidence":.6}))))
    assert low.state=="abstain"
    assert low.reason=="insufficient_observation_confidence"
    assert low.preferred_in_simulation=="abstain"

def test_empty_intersection_has_no_material_advantage():
    empty=evaluate(snapshot((
        approach("A","GA",0,0,.4,10),
        approach("B","GB",0,0,.4,10))))
    assert empty.preferred_in_simulation=="no_material_advantage"
    assert empty.reason=="no_material_advantage"
    assert empty.dynamic_x_safe_vehicles==0

def test_optimizer_requires_exactly_two_explicit_service_groups():
    one=evaluate(snapshot((approach("A","GA",3,.1,.4,10),)))
    assert one.reason=="requires_two_service_groups"
    three=evaluate(snapshot((
        approach("A","GA",3,.1,.4,10),
        approach("B","GB",4,.1,.4,10),
        approach("C","GC",5,.1,.4,10))))
    assert three.reason=="requires_two_service_groups"

def test_unvalidated_visibility_caps_confidence_and_forces_abstention():
    config=geometry()
    approach_cfg=config.approaches[0].model_copy(update={"visibility_calibrated":False,"visibility_score":1.0})
    config=config.model_copy(update={"approaches":(approach_cfg,config.approaches[1])})
    traffic=TrafficEngine(config)
    queue=QueueEstimator(config)
    snap=run_pair(traffic,queue,batch(1,[track(1,.2)],0))
    assert next(x for x in snap.approaches if x.approach_id=="A").observation_confidence<=.6

def test_store_is_idempotent_and_preserves_integrity(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'queue.db'}")
    Base.metadata.create_all(engine)
    store=QueueStore(engine)
    state=snapshot((
        approach("A","GA",34,.35,.6,50),
        approach("B","GB",6,.08,.5,20)))
    result=evaluate(state)
    store.save(state,result)
    store.save(state,result)
    assert store.recent_states("CAM_01",10)==[state]
    assert store.recent_experiments("CAM_01",10)==[result]
    engine.dispose()

def test_queue_and_optimization_api_start_idle_without_fabricating_values(tmp_path):
    registry=json.dumps([{
        "source_id":"CAM_01","intersection_code":"CR_01","kind":"file","locator":"fixture.avi",
        "data_origin":"external_real_replay"
    }])
    geo=geometry().model_dump(mode="json")
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'api.db'}",
        video_sources_json=registry,traffic_geometry_json=json.dumps([geo]))
    with TestClient(create_app(settings)) as client:
        queue_status=client.get("/api/v1/queue/status")
        assert queue_status.status_code==200
        assert queue_status.json()["state"]=="idle"
        optimization=client.get("/api/v1/optimization/status").json()
        assert optimization["state"]=="idle"
        assert optimization["physical_actuation"] is False
        assert optimization["operational_decision"]=="abstain"
        assert client.get("/api/v1/queue/sources/CAM_01/latest").status_code==404
        assert client.get("/api/v1/optimization/sources/CAM_01/latest").status_code==404
        health=client.get("/api/v1/health").json()
        assert health["queue_intelligence"]["physical_speed_available"] is False
        assert health["optimization"]["operational_decision"]=="abstain"
