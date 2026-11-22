from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from src.vision.contracts import DetectionBatch, Detection
from src.tracking.tracker import ByteTrackInspired, Track
from src.tracking.association import associate, iou
from src.tracking.service import TrackingService

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
SESSION=uuid4()

def det(x=.2,conf=.9,label="car"):
    return Detection(label=label,confidence=conf,xyxy=(x,.2,x+.2,.4))

def batch(n,dets=(),source="CAM_01",session=SESSION,at=None,model="a"*64):
    return DetectionBatch(source_id=source,intersection_code="CR_01",
        session_id=session,frame_sequence=n,received_at=BASE+timedelta(seconds=n*.1 if at is None else at),
        inferred_at=BASE+timedelta(seconds=n*.1 if at is None else at),
        model_sha256=model,purpose="validation_only",inference_ms=1,detections=tuple(dets))

def test_stable_ids_two_pass_and_no_duplicate_tracks():
    tracker=ByteTrackInspired()
    first=tracker.update(batch(1,[det()]))
    assert first.tracks[0].state=="tentative"
    second=tracker.update(batch(2,[det(.21)]))
    assert second.tracks[0].state=="confirmed"
    assert second.tracks[0].track_id==first.tracks[0].track_id
    third=tracker.update(batch(3,[det(.22,.35),det(.65,.35)]))
    assert len(third.tracks)==1
    assert third.tracks[0].track_id==first.tracks[0].track_id
    assert third.tracks[0].confidence==.35
    assert third.tracks[0].hits==3
    assert third.skipped_frames==0
    assert third.tracking_ms>=0

def test_loss_reacquisition_and_expiration():
    tracker=ByteTrackInspired()
    tracker.update(batch(1,[det()]))
    confirmed=tracker.update(batch(2,[det()]))
    missing=tracker.update(batch(4))
    assert missing.tracks==() and missing.lost_private==1
    assert missing.skipped_frames==1
    low=tracker.update(batch(5,[det(conf=.35)]))
    assert low.tracks==() # low confidence cannot reactivate a lost track
    back=tracker.update(batch(6,[det()]))
    assert back.tracks[0].track_id==confirmed.tracks[0].track_id
    assert back.tracks[0].state=="confirmed"
    new=tracker.update(batch(40,[det()],at=4))
    assert new.tracking_epoch!=back.tracking_epoch
    assert new.tracks[0].state=="tentative"

def test_tentative_does_not_survive_missing_observation():
    tracker=ByteTrackInspired()
    old=tracker.update(batch(1,[det()]))
    assert tracker.update(batch(2)).lost_private==0
    new=tracker.update(batch(3,[det()]))
    assert new.tracks[0].track_id!=old.tracks[0].track_id
    assert new.tracks[0].state=="tentative"

def test_sessions_models_and_order():
    tracker=ByteTrackInspired()
    a=tracker.update(batch(1,[det()]))
    with pytest.raises(ValueError,match="nonmonotonic"):
        tracker.update(batch(1,[det()]))
    b=tracker.update(batch(1,[det()],session=uuid4()))
    c=tracker.update(batch(2,[det()],session=b.session_id,model="b"*64))
    d=tracker.update(batch(3,[det()],session=b.session_id,model="b"*64,at=0))
    assert len({a.tracking_epoch,b.tracking_epoch,c.tracking_epoch,d.tracking_epoch})==4
    assert all(r.tracks[0].state=="tentative" for r in (a,b,c,d))
    with pytest.raises(ValueError):
        ByteTrackInspired(high=.2,low=.3)

def test_assignment_is_one_to_one_and_class_gated():
    tracker=ByteTrackInspired()
    a=tracker.update(batch(1,[det(.2),det(.65,label="truck")]))
    b=tracker.update(batch(2,[det(.65,label="truck"),det(.21),det(.2,label="bus")]))
    ids={t.label:t.track_id for t in a.tracks}
    assert len({t.track_id for t in b.tracks})==3
    assert all(t.track_id==ids[t.label] for t in b.tracks if t.label in ids)
    assert next(t for t in b.tracks if t.label=="bus").state=="tentative"
    assert iou((0,0,0,0),(0,0,0,0))==0
    assert iou((0,0,1,1),(0,0,1,1))==1
    assert associate([], [det()], .3)==([],[],[0])
    assert associate([Track.create(1,det(),batch(1))], [], .3)==([],[0],[])
    assert not associate([Track.create(1,det(),batch(1))],[det(label="bus")],.3)[0]

def test_bounds_and_expiry_without_large_batch_gap(monkeypatch):
    monkeypatch.setattr("src.tracking.tracker.MAX_TRACKS",2)
    tracker=ByteTrackInspired()
    a=tracker.update(batch(1,[det(.1),det(.4),det(.7)]))
    assert len(a.tracks)==2
    tracker.update(batch(2,[det(.1),det(.4)]))
    for n in range(3,26):
        last=tracker.update(batch(n))
    assert last.lost_private==0

def test_service_isolates_sources_errors_and_stale_results():
    one=batch(1,[det()])
    two=batch(1,[det()],source="CAM_02")
    current={"CAM_01":one,"CAM_02":two}
    sessions={k:SimpleNamespace(state="running") for k in current}
    vision=SimpleNamespace(video=SimpleNamespace(sessions=sessions),spec=SimpleNamespace(confidence=.25),
                           state="ready",valid_result=current.get)
    service=TrackingService(vision)
    service.consume(one);service.consume(two)
    assert service.latest("CAM_01").tracking_epoch!=service.latest("CAM_02").tracking_epoch
    service.consume(one)
    assert service.latest("CAM_01") is None
    assert service.latest("CAM_02") is not None
    assert service.status()["state"]=="degraded"
    assert service.status()["failed"]==1
    newer=batch(2,[det()])
    current["CAM_01"]=newer
    service.consume(newer)
    assert service.status()["state"]=="ready"
    current["CAM_02"]=batch(2,source="CAM_02",session=uuid4())
    assert service.latest("CAM_02") is None
    assert len(service.status()["sources"])==1
    service.clear()
    assert service.latest("CAM_01") is None
    vision.state="error"
    assert service.status()["state"]=="not_loaded"
