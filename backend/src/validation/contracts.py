import json
from pathlib import Path
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from src.analytics.contracts import Contract
from src.vision.contracts import VehicleClass

GateId=Literal[
    "synthetic_demo_dataset","authorized_model","physical_camera","calibration",
    "field_ground_truth","hardware_benchmark","recovery_drill","human_acceptance"
]
EvidenceState=Literal["ready","not_run","blocked","failed","pending_human"]
EvidenceOrigin=Literal["external","ci","synthetic"]

PILOT_REQUIRED={
    "authorized_model","physical_camera","calibration","field_ground_truth",
    "hardware_benchmark","recovery_drill","human_acceptance"
}
FIELD_ONLY={
    "authorized_model","physical_camera","calibration","field_ground_truth",
    "hardware_benchmark","human_acceptance"
}

class EvidenceRecord(Contract):
    gate: GateId
    state: EvidenceState
    origin: EvidenceOrigin
    artifact_sha256: str | None = Field(default=None,pattern=r"^[0-9a-f]{64}$")
    reference: str | None = Field(default=None,min_length=1,max_length=240)
    executed_at: AwareDatetime | None = None
    note: str | None = Field(default=None,min_length=1,max_length=500)
    human_authorized: bool = False

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.state=="ready":
            if self.gate=="human_acceptance":
                if not self.human_authorized or not self.reference or not self.executed_at:
                    raise ValueError("human acceptance requires explicit authorization")
            elif not self.artifact_sha256 or not self.executed_at:
                raise ValueError("ready evidence requires artifact and execution time")
            if self.origin=="synthetic" and self.gate in PILOT_REQUIRED:
                raise ValueError("synthetic evidence cannot satisfy pilot gate")
        if self.state=="failed" and not self.note:
            raise ValueError("failed evidence requires note")
        return self

def load_evidence(raw):
    try:
        if len(raw)>128000:
            raise ValueError
        data=json.loads(raw)
        if not isinstance(data,list) or len(data)>32:
            raise ValueError
        records=tuple(EvidenceRecord.model_validate(item) for item in data)
        if len({item.gate for item in records})!=len(records):
            raise ValueError
        return records
    except (TypeError,ValueError):
        raise ValueError("invalid validation evidence") from None

class DatasetManifest(Contract):
    schema_version: Literal[1]=1
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{2,80}$")
    origin: Literal["synthetic","field"]
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{2,80}$")
    intersection_code: str = Field(pattern=r"^[A-Z0-9_-]{2,80}$")
    video_filename: str = Field(min_length=1,max_length=160)
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: str = Field(min_length=2,max_length=240)
    license_ref: str = Field(min_length=2,max_length=240)
    authorization_ref: str = Field(min_length=2,max_length=240)
    recorded_at: AwareDatetime
    fps: float = Field(gt=0,le=120)
    width: int = Field(ge=64,le=7680)
    height: int = Field(ge=64,le=4320)
    frame_count: int = Field(ge=1)
    classes: tuple[VehicleClass,...] = Field(min_length=1,max_length=5)

    @model_validator(mode="after")
    def safe_filename(self):
        path=Path(self.video_filename)
        if path.is_absolute() or ".." in path.parts or path.name!=self.video_filename or path.suffix.lower() not in {".avi",".mp4",".mkv",".mov"}:
            raise ValueError("invalid video filename")
        if len(set(self.classes))!=len(self.classes):
            raise ValueError("duplicate classes")
        return self

class GroundTruthObject(Contract):
    frame_sequence: int = Field(ge=1)
    object_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")
    label: VehicleClass
    xyxy: tuple[float,float,float,float]

    @model_validator(mode="after")
    def valid_box(self):
        x1,y1,x2,y2=self.xyxy
        if not 0<=x1<x2<=1 or not 0<=y1<y2<=1:
            raise ValueError("invalid normalized box")
        return self

class PredictedObject(Contract):
    frame_sequence: int = Field(ge=1)
    label: VehicleClass
    confidence: float = Field(ge=0,le=1)
    xyxy: tuple[float,float,float,float]
    track_id: int | None = Field(default=None,ge=1)

    @model_validator(mode="after")
    def valid_box(self):
        x1,y1,x2,y2=self.xyxy
        if not 0<=x1<x2<=1 or not 0<=y1<y2<=1:
            raise ValueError("invalid normalized box")
        return self

class CountValue(Contract):
    line_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    direction: Literal["negative_to_positive","positive_to_negative"]
    label: VehicleClass | None = None
    count: int = Field(ge=0)

class GroundTruth(Contract):
    schema_version: Literal[1]=1
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{2,80}$")
    annotations: tuple[GroundTruthObject,...] = Field(max_length=200000)
    counts: tuple[CountValue,...] = Field(default=(),max_length=5000)

    @model_validator(mode="after")
    def unique_entries(self):
        seen=set()
        for item in self.annotations:
            key=(item.frame_sequence,item.object_id)
            if key in seen:
                raise ValueError("duplicate ground truth object in frame")
            seen.add(key)
        keys=[(x.line_id,x.direction,x.label) for x in self.counts]
        if len(keys)!=len(set(keys)):
            raise ValueError("duplicate ground truth count key")
        return self

class Predictions(Contract):
    schema_version: Literal[1]=1
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{2,80}$")
    annotations: tuple[PredictedObject,...] = Field(max_length=200000)
    counts: tuple[CountValue,...] = Field(default=(),max_length=5000)

    @model_validator(mode="after")
    def unique_entries(self):
        per_frame_tracks=set()
        for item in self.annotations:
            if item.track_id is None:
                continue
            key=(item.frame_sequence,item.track_id)
            if key in per_frame_tracks:
                raise ValueError("duplicate predicted track in frame")
            per_frame_tracks.add(key)
        keys=[(x.line_id,x.direction,x.label) for x in self.counts]
        if len(keys)!=len(set(keys)):
            raise ValueError("duplicate predicted count key")
        return self

class EvaluationThresholds(Contract):
    purpose: Literal["engineering_test","synthetic_demo","field_acceptance"]
    approval_reference: str = Field(min_length=2,max_length=240)
    approved_at: AwareDatetime
    detection_macro_f1: float = Field(ge=0,le=1)
    tracking_match_recall: float = Field(ge=0,le=1)
    max_identity_switch_rate: float = Field(ge=0,le=1)
    count_accuracy: float = Field(ge=0,le=1)

class EvaluationRequest(Contract):
    manifest: DatasetManifest
    ground_truth: GroundTruth
    predictions: Predictions
    thresholds: EvaluationThresholds
    iou_threshold: float = Field(default=.5,ge=.1,le=.9)

    @model_validator(mode="after")
    def same_dataset(self):
        if self.ground_truth.dataset_id!=self.manifest.dataset_id or self.predictions.dataset_id!=self.manifest.dataset_id:
            raise ValueError("dataset id mismatch")
        allowed=set(self.manifest.classes)
        for item in (*self.ground_truth.annotations,*self.predictions.annotations):
            if item.frame_sequence>self.manifest.frame_count:
                raise ValueError("annotation beyond manifest frame count")
            if item.label not in allowed:
                raise ValueError("annotation class outside manifest")
        for item in (*self.ground_truth.counts,*self.predictions.counts):
            if item.label is not None and item.label not in allowed:
                raise ValueError("count class outside manifest")
        if self.manifest.origin=="field":
            if self.thresholds.purpose!="field_acceptance":
                raise ValueError("field dataset requires field acceptance thresholds")
            if self.thresholds.approved_at>self.manifest.recorded_at:
                raise ValueError("field thresholds must be approved before capture")
        elif self.thresholds.purpose=="field_acceptance":
            raise ValueError("field acceptance thresholds cannot be applied to synthetic dataset")
        return self

class ClassMetric(Contract):
    label: VehicleClass
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    precision: float = Field(ge=0,le=1)
    recall: float = Field(ge=0,le=1)
    f1: float = Field(ge=0,le=1)

class EvaluationResult(Contract):
    schema_version: Literal[1]=1
    dataset_id: str
    origin: Literal["synthetic","field"]
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ground_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thresholds_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    iou_threshold: float
    per_class: tuple[ClassMetric,...]
    detection_macro_f1: float = Field(ge=0,le=1)
    tracking_match_recall: float = Field(ge=0,le=1)
    identity_switches: int = Field(ge=0)
    identity_switch_rate: float = Field(ge=0,le=1)
    count_mae: float = Field(ge=0)
    count_accuracy: float = Field(ge=0,le=1)
    meets_supplied_thresholds: bool
    operationally_validated: Literal[False]=False
    physical_actuation: Literal[False]=False

class CalibrationChecklist(Contract):
    schema_version: Literal[1]=1
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{2,80}$")
    intersection_code: str = Field(pattern=r"^[A-Z0-9_-]{2,80}$")
    camera_mount_fixed: bool
    source_intersection_verified: bool
    resolution_verified: bool
    timestamp_verified: bool
    geometry_reviewed: bool
    line_directions_verified: bool
    occlusion_reviewed: bool
    privacy_reviewed: bool

def calibration_assessment(checklist):
    values=checklist.model_dump()
    pending=[key for key,value in values.items() if key not in {"schema_version","source_id","intersection_code"} and value is not True]
    return {"state":"ready" if not pending else "blocked","pending":pending}
