import asyncio
import hashlib
import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.analytics.contracts import CountingLine,SourceGeometry
from src.config import Settings
from src.main import create_app
from src.validation.contracts import (
    CalibrationChecklist,CountValue,DatasetManifest,EvidenceRecord,EvaluationRequest,
    EvaluationThresholds,GroundTruth,GroundTruthObject,PredictedDetection,PredictedTrack,
    Predictions,calibration_assessment,load_evidence
)
from src.validation.engine import evaluate,iou
from src.validation.io import sha256_file,verify_video
from src.validation.runner import run_case
from src.validation.service import ValidationService
from src.vision.contracts import ModelSpec

NOW=datetime(2026,11,24,tzinfo=timezone.utc)

def manifest(**changes):
    values=dict(dataset_id="case-01",origin="field",source_id="CAM_01",
        intersection_code="CR_01",video_filename="case.mp4",video_sha256="a"*64,
        provenance="authorized field capture",license_ref="internal authorization",
        authorization_ref="field-capture-ticket",recorded_at=NOW,
        fps=10,width=640,height=360,frame_count=10,classes=("car","bus"))
    values.update(changes)
    return DatasetManifest(**values)

def truth():
    return GroundTruth(dataset_id="case-01",annotations=(
        GroundTruthObject(frame_sequence=1,object_id="car-1",label="car",xyxy=(.1,.1,.3,.3)),
        GroundTruthObject(frame_sequence=2,object_id="car-1",label="car",xyxy=(.2,.1,.4,.3)),
        GroundTruthObject(frame_sequence=2,object_id="bus-1",label="bus",xyxy=(.6,.2,.9,.7)),
    ),counts=(
        CountValue(line_id="L1",direction="negative_to_positive",label="car",count=1),
        CountValue(line_id="L1",direction="negative_to_positive",label="bus",count=1),
    ))

def predictions(detections=None,tracks=None,counts=None):
    if detections is None:
        detections=(
            PredictedDetection(frame_sequence=1,label="car",confidence=.9,xyxy=(.1,.1,.3,.3)),
            PredictedDetection(frame_sequence=2,label="car",confidence=.9,xyxy=(.2,.1,.4,.3)),
            PredictedDetection(frame_sequence=2,label="bus",confidence=.8,xyxy=(.6,.2,.9,.7)),
        )
    if tracks is None:
        tracks=(
            PredictedTrack(frame_sequence=1,track_id=1,label="car",confidence=.9,xyxy=(.1,.1,.3,.3)),
            PredictedTrack(frame_sequence=2,track_id=1,label="car",confidence=.9,xyxy=(.2,.1,.4,.3)),
            PredictedTrack(frame_sequence=2,track_id=2,label="bus",confidence=.8,xyxy=(.6,.2,.9,.7)),
        )
    if counts is None:
        counts=(
            CountValue(line_id="L1",direction="negative_to_positive",label="car",count=1),
            CountValue(line_id="L1",direction="negative_to_positive",label="bus",count=1),
        )
    return Predictions(dataset_id="case-01",model_sha256="b"*64,geometry_sha256="c"*64,
                       detections=detections,tracks=tracks,counts=counts)

def thresholds(**changes):
    values=dict(purpose="field_acceptance",approval_reference="approved-thresholds-v1",
                approved_at=NOW-timedelta(minutes=5),
                detection_macro_f1=.8,tracking_match_recall=.8,
                max_identity_switch_rate=.1,count_accuracy=.8)
    values.update(changes)
    return EvaluationThresholds(**values)

def request(predicted=None,**changes):
    values=dict(manifest=manifest(),ground_truth=truth(),
        predictions=predicted or predictions(),thresholds=thresholds(),iou_threshold=.5)
    values.update(changes)
    return EvaluationRequest(**values)

def test_iou_and_perfect_evaluation_are_deterministic():
    assert iou((0,0,1,1),(0,0,1,1))==1
    assert iou((0,0,.2,.2),(.8,.8,1,1))==0
    first=evaluate(request())
    second=evaluate(request())
    assert first==second
    assert first.input_sha256==second.input_sha256
    assert first.result_sha256==second.result_sha256
    assert first.manifest_sha256 and first.ground_truth_sha256
    assert first.predictions_sha256 and first.thresholds_sha256
    assert first.detection_macro_f1==1
    assert first.tracking_match_recall==1
    assert first.identity_switches==0
    assert first.identity_switch_rate==0
    assert first.count_mae==0
    assert first.count_accuracy==1
    assert first.meets_supplied_thresholds is True
    assert first.operationally_validated is False
    assert first.physical_actuation is False
    assert {item.label for item in first.per_class}=={"car","bus"}

def test_degraded_evaluation_separates_detection_tracking_and_count_failures():
    detected=(
        PredictedDetection(frame_sequence=1,label="car",confidence=.9,xyxy=(.1,.1,.3,.3)),
        PredictedDetection(frame_sequence=2,label="car",confidence=.9,xyxy=(.2,.1,.4,.3)),
        PredictedDetection(frame_sequence=3,label="bus",confidence=.8,xyxy=(.6,.2,.9,.7)),
    )
    tracked=(
        PredictedTrack(frame_sequence=1,track_id=1,label="car",confidence=.9,xyxy=(.1,.1,.3,.3)),
        PredictedTrack(frame_sequence=2,track_id=9,label="car",confidence=.9,xyxy=(.2,.1,.4,.3)),
    )
    counted=(
        CountValue(line_id="L1",direction="negative_to_positive",label="car",count=2),
        CountValue(line_id="L1",direction="negative_to_positive",label="bus",count=0),
    )
    result=evaluate(request(predictions(detected,tracked,counted)))
    assert result.detection_macro_f1<1
    assert result.tracking_match_recall==pytest.approx(2/3)
    assert result.identity_switches==1
    assert result.identity_switch_rate==pytest.approx(.5)
    assert result.count_mae==1
    assert result.count_accuracy==0
    assert result.meets_supplied_thresholds is False

def test_contracts_reject_provenance_mismatches_duplicates_and_post_capture_thresholds():
    with pytest.raises(ValidationError):
        EvaluationRequest(manifest=manifest(frame_count=1),ground_truth=truth(),
            predictions=predictions(),thresholds=thresholds())
    with pytest.raises(ValidationError):
        EvaluationRequest(manifest=manifest(classes=("car",)),ground_truth=truth(),
            predictions=predictions(),thresholds=thresholds())
    with pytest.raises(ValidationError):
        EvaluationRequest(manifest=manifest(),ground_truth=truth(),predictions=predictions(),
            thresholds=thresholds(approved_at=NOW+timedelta(seconds=1)))
    synthetic_manifest=manifest(origin="synthetic",authorization_ref="synthetic-generation",
                                provenance="synthetic test",recorded_at=NOW)
    with pytest.raises(ValidationError):
        EvaluationRequest(manifest=synthetic_manifest,ground_truth=truth(),
            predictions=predictions(),thresholds=thresholds())
    with pytest.raises(ValidationError):
        GroundTruth(dataset_id="case-01",annotations=(
            GroundTruthObject(frame_sequence=1,object_id="same",label="car",xyxy=(.1,.1,.2,.2)),
            GroundTruthObject(frame_sequence=1,object_id="same",label="car",xyxy=(.2,.2,.3,.3)),
        ))
    with pytest.raises(ValidationError):
        Predictions(dataset_id="case-01",model_sha256="b"*64,geometry_sha256="c"*64,detections=(),
            tracks=(
              PredictedTrack(frame_sequence=1,track_id=3,label="car",confidence=.9,xyxy=(.1,.1,.2,.2)),
              PredictedTrack(frame_sequence=1,track_id=3,label="car",confidence=.8,xyxy=(.2,.2,.3,.3)),
            ))
    duplicate=CountValue(line_id="L1",direction="negative_to_positive",label="car",count=1)
    with pytest.raises(ValidationError):
        GroundTruth(dataset_id="case-01",annotations=(),counts=(duplicate,duplicate))

def test_evidence_cannot_fake_field_readiness():
    with pytest.raises(ValidationError):
        EvidenceRecord(gate="authorized_model",state="ready",origin="synthetic",
            artifact_sha256="b"*64,executed_at=NOW)
    with pytest.raises(ValidationError):
        EvidenceRecord(gate="human_acceptance",state="ready",origin="external",
            reference="ticket-1",executed_at=NOW,human_authorized=False)
    with pytest.raises(ValueError):
        load_evidence(json.dumps([
            {"gate":"recovery_drill","state":"not_run","origin":"ci"},
            {"gate":"recovery_drill","state":"not_run","origin":"ci"}
        ]))

def test_validation_service_stays_blocked_until_all_pilot_evidence_exists():
    video=SimpleNamespace(sessions={})
    vision=SimpleNamespace(status=lambda:{"configured":False,"purpose":None})
    status=ValidationService(video,vision).status()
    assert status["framework_ready"] is True
    assert status["pilot_ready"] is False
    assert status["pilot_decision"]=="blocked_by_field_evidence"
    assert "human_acceptance" in status["missing_evidence"]
    assert status["physical_actuation"] is False
    summary=ValidationService(video,vision).health_status()
    assert "gates" not in summary and "runtime_observation" not in summary
    records=[]
    for gate in (
        "authorized_model","physical_camera","calibration","field_ground_truth",
        "hardware_benchmark","recovery_drill"
    ):
        records.append(EvidenceRecord(gate=gate,state="ready",
            origin="ci" if gate=="recovery_drill" else "external",
            artifact_sha256=hashlib.sha256(gate.encode()).hexdigest(),executed_at=NOW))
    records.append(EvidenceRecord(gate="human_acceptance",state="ready",origin="external",
        reference="approved-field-acceptance",executed_at=NOW,human_authorized=True))
    ready=ValidationService(video,vision,records).status()
    assert ready["pilot_ready"] is True
    assert ready["missing_evidence"]==[]
    assert ready["pilot_decision"]=="ready_for_supervised_pilot"

def test_calibration_requires_every_field_check():
    blocked=CalibrationChecklist(source_id="CAM_01",intersection_code="CR_01",
        camera_mount_fixed=True,source_intersection_verified=True,resolution_verified=True,
        timestamp_verified=False,geometry_reviewed=True,line_directions_verified=True,
        occlusion_reviewed=True,privacy_reviewed=True)
    assert calibration_assessment(blocked)=={"state":"blocked","pending":["timestamp_verified"]}
    ready=blocked.model_copy(update={"timestamp_verified":True})
    assert calibration_assessment(ready)=={"state":"ready","pending":[]}

def test_video_verification_binds_sha_and_decoder_metadata(tmp_path):
    path=tmp_path/"case.mp4"
    path.write_bytes(b"authorized-fixture")
    sha=sha256_file(path)
    class Capture:
        def __init__(self,*_): pass
        def isOpened(self): return True
        def get(self,key):
            return {
                cv2.CAP_PROP_FRAME_WIDTH:640,
                cv2.CAP_PROP_FRAME_HEIGHT:360,
                cv2.CAP_PROP_FPS:10,
                cv2.CAP_PROP_FRAME_COUNT:10,
            }[key]
        def release(self): pass
    checked=verify_video(manifest(video_sha256=sha),path,Capture)
    assert checked["sha256"]==sha and checked["decoder"]=="opencv"
    with pytest.raises(ValueError,match="sha256"):
        verify_video(manifest(video_sha256="0"*64),path,Capture)

def test_offline_runner_reuses_detector_tracker_and_traffic_engine(tmp_path):
    case_manifest=manifest(frame_count=3,classes=("car",))
    spec=ModelSpec(filename="model.onnx",sha256="d"*64,provenance="test",
                   license_ref="test-license",purpose="authorized_candidate",confidence=.25)
    geometry=SourceGeometry(source_id="CAM_01",intersection_code="CR_01",
        lines=(CountingLine(line_id="L1",start=(.5,0),end=(.5,1)),))
    frames=[np.zeros((360,640,3),dtype=np.uint8) for _ in range(3)]
    class Capture:
        def __init__(self,*_): self.index=0
        def isOpened(self): return True
        def read(self):
            if self.index>=len(frames): return False,None
            frame=frames[self.index]; self.index+=1; return True,frame
        def release(self): pass
    positions=[(.2,.3),(.25,.35),(.65,.75)]
    class Worker:
        def __init__(self,*_): self.index=0
        async def open(self): pass
        async def close(self): pass
        async def infer(self,_jpeg):
            x1,x2=positions[self.index]; self.index+=1
            return {"inference_ms":1.0,"detections":[{"label":"car","confidence":.9,"xyxy":[x1,.3,x2,.6]}]}
    result=asyncio.run(run_case(case_manifest,tmp_path/"case.mp4",spec,tmp_path,geometry,
        worker_factory=Worker,capture_factory=Capture,verify=lambda *_: {}))
    assert len(result.detections)==3
    assert len(result.tracks)==2
    count={(item.line_id,item.direction):item.count for item in result.counts}
    assert count[("L1","positive_to_negative")]==1
    assert result.model_sha256=="d"*64

def test_validation_api_reports_blocked_not_fake_ready(tmp_path):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'db.sqlite'}")
    with TestClient(create_app(settings)) as client:
        response=client.get("/api/v1/validation/status")
        assert response.status_code==200
        payload=response.json()
        assert payload["framework_ready"] is True
        assert payload["pilot_ready"] is False
        assert payload["operational_decision"]=="abstain"
        health=client.get("/health")
        summary=health.json()["validation"]
        assert summary["pilot_ready"] is False
        assert "gates" not in summary
        assert "runtime_observation" not in summary

def test_invalid_evidence_config_is_visible_without_faking_gate(tmp_path):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'invalid.db'}",
                      validation_evidence_json='{"invalid":true}')
    with TestClient(create_app(settings)) as client:
        payload=client.get("/api/v1/validation/status").json()
        assert payload["state"]=="error"
        assert payload["framework_ready"] is False
        assert payload["pilot_ready"] is False
        assert payload["error_code"]=="validation_evidence_invalid"
