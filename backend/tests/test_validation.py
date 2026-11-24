import hashlib
import json
from datetime import datetime,timezone
from types import SimpleNamespace
import cv2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.config import Settings
from src.main import create_app
from src.validation.contracts import (
    CalibrationChecklist,CountValue,DatasetManifest,EvidenceRecord,EvaluationRequest,
    EvaluationThresholds,GroundTruth,GroundTruthObject,PredictedObject,Predictions,
    calibration_assessment,load_evidence
)
from src.validation.engine import evaluate,iou
from src.validation.io import sha256_file,verify_video
from src.validation.service import ValidationService

NOW=datetime(2026,11,24,tzinfo=timezone.utc)

def manifest(**changes):
    values=dict(dataset_id="case-01",origin="field",source_id="CAM_01",
        intersection_code="CR_01",video_filename="case.mp4",video_sha256="a"*64,
        provenance="authorized field capture",license_ref="internal authorization",
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

def perfect_predictions():
    return Predictions(dataset_id="case-01",annotations=(
        PredictedObject(frame_sequence=1,label="car",confidence=.9,xyxy=(.1,.1,.3,.3),track_id=1),
        PredictedObject(frame_sequence=2,label="car",confidence=.9,xyxy=(.2,.1,.4,.3),track_id=1),
        PredictedObject(frame_sequence=2,label="bus",confidence=.8,xyxy=(.6,.2,.9,.7),track_id=2),
    ),counts=(
        CountValue(line_id="L1",direction="negative_to_positive",label="car",count=1),
        CountValue(line_id="L1",direction="negative_to_positive",label="bus",count=1),
    ))

def thresholds(**changes):
    values=dict(detection_macro_f1=.8,tracking_match_recall=.8,
                max_identity_switch_rate=.1,count_accuracy=.8)
    values.update(changes)
    return EvaluationThresholds(**values)

def request(predictions=None,**changes):
    values=dict(manifest=manifest(),ground_truth=truth(),
        predictions=predictions or perfect_predictions(),thresholds=thresholds(),iou_threshold=.5)
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

def test_degraded_evaluation_detects_misses_false_positive_switch_and_count_error():
    predictions=Predictions(dataset_id="case-01",annotations=(
        PredictedObject(frame_sequence=1,label="car",confidence=.9,xyxy=(.1,.1,.3,.3),track_id=1),
        PredictedObject(frame_sequence=2,label="car",confidence=.9,xyxy=(.2,.1,.4,.3),track_id=9),
        PredictedObject(frame_sequence=3,label="bus",confidence=.8,xyxy=(.6,.2,.9,.7),track_id=7),
    ),counts=(
        CountValue(line_id="L1",direction="negative_to_positive",label="car",count=2),
        CountValue(line_id="L1",direction="negative_to_positive",label="bus",count=0),
    ))
    result=evaluate(request(predictions))
    assert result.detection_macro_f1<1
    assert result.tracking_match_recall==pytest.approx(2/3)
    assert result.identity_switches==1
    assert result.identity_switch_rate==pytest.approx(.5)
    assert result.count_mae==1
    assert result.count_accuracy==0
    assert result.meets_supplied_thresholds is False

def test_contracts_reject_provenance_mismatches_and_duplicates():
    with pytest.raises(ValidationError):
        EvaluationRequest(manifest=manifest(frame_count=1),ground_truth=truth(),
            predictions=perfect_predictions(),thresholds=thresholds())
    with pytest.raises(ValidationError):
        EvaluationRequest(manifest=manifest(classes=("car",)),ground_truth=truth(),
            predictions=perfect_predictions(),thresholds=thresholds())
    with pytest.raises(ValidationError):
        GroundTruth(dataset_id="case-01",annotations=(
            GroundTruthObject(frame_sequence=1,object_id="same",label="car",xyxy=(.1,.1,.2,.2)),
            GroundTruthObject(frame_sequence=1,object_id="same",label="car",xyxy=(.2,.2,.3,.3)),
        ))
    with pytest.raises(ValidationError):
        Predictions(dataset_id="case-01",annotations=(
            PredictedObject(frame_sequence=1,label="car",confidence=.9,xyxy=(.1,.1,.2,.2),track_id=3),
            PredictedObject(frame_sequence=1,label="car",confidence=.8,xyxy=(.2,.2,.3,.3),track_id=3),
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
        def __init__(self,*_): self.released=False
        def isOpened(self): return True
        def get(self,key):
            return {
                cv2.CAP_PROP_FRAME_WIDTH:640,
                cv2.CAP_PROP_FRAME_HEIGHT:360,
                cv2.CAP_PROP_FPS:10,
                cv2.CAP_PROP_FRAME_COUNT:10,
            }[key]
        def release(self): self.released=True
    checked=verify_video(manifest(video_sha256=sha),path,Capture)
    assert checked["sha256"]==sha and checked["decoder"]=="opencv"
    with pytest.raises(ValueError,match="sha256"):
        verify_video(manifest(video_sha256="0"*64),path,Capture)

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
        assert health.json()["validation"]["pilot_ready"] is False

def test_invalid_evidence_config_is_visible_without_faking_gate(tmp_path):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'invalid.db'}",
                      validation_evidence_json='{"invalid":true}')
    with TestClient(create_app(settings)) as client:
        payload=client.get("/api/v1/validation/status").json()
        assert payload["state"]=="error"
        assert payload["framework_ready"] is False
        assert payload["pilot_ready"] is False
        assert payload["error_code"]=="validation_evidence_invalid"
