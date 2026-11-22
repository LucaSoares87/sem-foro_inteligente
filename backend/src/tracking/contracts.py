from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from src.vision.contracts import VehicleClass

class TrackObservation(BaseModel):
    model_config = ConfigDict(frozen=True,extra="forbid",allow_inf_nan=False)
    track_id: int = Field(ge=1)
    label: VehicleClass
    state: Literal["tentative","confirmed"]
    confidence: float = Field(ge=0,le=1)
    xyxy: tuple[float,float,float,float]
    hits: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_box(self):
        x1,y1,x2,y2=self.xyxy
        if not 0<=x1<x2<=1 or not 0<=y1<y2<=1:
            raise ValueError("invalid track box")
        return self

class TrackBatch(BaseModel):
    model_config = ConfigDict(frozen=True,extra="forbid",allow_inf_nan=False)
    schema_version: Literal[1]=1
    source_id: str
    intersection_code: str
    session_id: UUID
    tracking_epoch: UUID
    frame_sequence: int = Field(ge=1)
    received_at: AwareDatetime
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Literal["validation_only","authorized_candidate"]
    algorithm: Literal["bytetrack_inspired_v1"]="bytetrack_inspired_v1"
    tracking_ms: float = Field(ge=0)
    skipped_frames: int = Field(ge=0)
    lost_private: int = Field(ge=0,le=200)
    tracks: tuple[TrackObservation,...] = Field(max_length=100)
