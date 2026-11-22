from pathlib import Path
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_DETECTIONS = 100
VehicleClass = Literal["bicycle", "car", "motorcycle", "bus", "truck"]
CLASSES = {1:"bicycle",2:"car",3:"motorcycle",5:"bus",7:"truck"}

class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    filename: str = Field(min_length=1,max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance: str = Field(min_length=1,max_length=160)
    license_ref: str = Field(min_length=1,max_length=160)
    purpose: Literal["validation_only","authorized_candidate"] = "validation_only"
    confidence: float = Field(default=.25,ge=.05,le=.95)
    nms_iou: float = Field(default=.45,ge=.1,le=.9)

    def resolve(self, root):
        root = Path(root).resolve()
        relative = Path(self.filename)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".onnx":
            raise ValueError("invalid model path")
        path = (root/relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file() or not 0<path.stat().st_size<=MAX_MODEL_BYTES:
            raise ValueError("invalid model artifact")
        return path

class Detection(BaseModel):
    model_config = ConfigDict(frozen=True,extra="forbid",allow_inf_nan=False)
    label: VehicleClass
    confidence: float = Field(ge=0,le=1)
    xyxy: tuple[float,float,float,float]

    @model_validator(mode="after")
    def validate_box(self):
        x1,y1,x2,y2=self.xyxy
        if not 0<=x1<x2<=1 or not 0<=y1<y2<=1:
            raise ValueError("invalid normalized box")
        return self

class DetectionBatch(BaseModel):
    model_config = ConfigDict(frozen=True,extra="forbid",allow_inf_nan=False)
    schema_version: Literal[1] = 1
    source_id: str
    intersection_code: str
    session_id: UUID
    frame_sequence: int = Field(ge=1)
    received_at: AwareDatetime
    inferred_at: AwareDatetime
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Literal["validation_only","authorized_candidate"]
    inference_ms: float = Field(ge=0)
    detections: tuple[Detection,...] = Field(max_length=MAX_DETECTIONS)
