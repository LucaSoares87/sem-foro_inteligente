import json
from math import hypot
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Point = tuple[float,float]
Box = tuple[float,float,float,float]
MAX_REGIONS = 8
MAX_LINES = 8
MAX_APPROACHES = 8

class Contract(BaseModel):
    model_config = ConfigDict(frozen=True,extra="forbid",allow_inf_nan=False)

class Region(Contract):
    region_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    xyxy: Box

    @model_validator(mode="after")
    def validate_geometry(self):
        x1,y1,x2,y2=self.xyxy
        if not 0<=x1<x2<=1 or not 0<=y1<y2<=1 or (x2-x1)*(y2-y1)<.0001:
            raise ValueError("invalid ROI rectangle")
        return self

class CountingLine(Contract):
    line_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    start: Point
    end: Point
    deadband: float = Field(default=.015,ge=.001,le=.05)

    @model_validator(mode="after")
    def validate_geometry(self):
        if not all(0<=v<=1 for v in (*self.start,*self.end)):
            raise ValueError("line outside frame")
        if hypot(self.end[0]-self.start[0],self.end[1]-self.start[1])<.02:
            raise ValueError("line too short")
        return self

class QueueApproachConfig(Contract):
    approach_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    service_group: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    region_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    discharge_line_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    discharge_direction: Literal["negative_to_positive","positive_to_negative"]
    storage_capacity_vehicles: int = Field(strict=True,ge=1,le=200)
    stop_speed_normalized_per_s: float = Field(default=.015,ge=.001,le=.2)
    min_stop_seconds: float = Field(default=1.0,ge=.25,le=10)
    rate_window_seconds: float = Field(default=15.0,ge=5,le=60)
    visibility_score: float = Field(default=.5,ge=.1,le=1)
    visibility_calibrated: bool = False

class SourceGeometry(Contract):
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{2,80}$")
    intersection_code: str = Field(pattern=r"^[A-Z0-9_-]{2,80}$")
    regions: tuple[Region,...] = Field(default=(),max_length=MAX_REGIONS)
    lines: tuple[CountingLine,...] = Field(default=(),max_length=MAX_LINES)
    approaches: tuple[QueueApproachConfig,...] = Field(default=(),max_length=MAX_APPROACHES)
    max_gap_frames: int = Field(default=5,strict=True,ge=1,le=30)
    max_gap_seconds: float = Field(default=.75,ge=.1,le=2)

    @model_validator(mode="after")
    def validate_registry(self):
        if not self.regions and not self.lines:
            raise ValueError("no geometry configured")
        if len({r.region_id for r in self.regions})!=len(self.regions) or len({l.line_id for l in self.lines})!=len(self.lines):
            raise ValueError("duplicate geometry id")
        if len({a.approach_id for a in self.approaches})!=len(self.approaches):
            raise ValueError("duplicate queue approach id")
        regions={r.region_id for r in self.regions}
        lines={l.line_id for l in self.lines}
        for approach in self.approaches:
            if approach.region_id not in regions or approach.discharge_line_id not in lines:
                raise ValueError("queue approach references unknown geometry")
        return self

def load_geometry(raw,registered):
    try:
        if len(raw)>65536:
            raise ValueError
        data=json.loads(raw)
        if not isinstance(data,list) or len(data)>8:
            raise ValueError
        configs=[SourceGeometry.model_validate(item) for item in data]
        if len({item.source_id for item in configs})!=len(configs):
            raise ValueError
        for item in configs:
            if registered.get(item.source_id)!=item.intersection_code:
                raise ValueError
        return {item.source_id:item for item in configs}
    except (TypeError,ValueError):
        raise ValueError("invalid traffic geometry registry") from None

class RegionMetric(Contract):
    region_id: str
    confirmed_visible: int = Field(ge=0,le=100)
    image_coverage_pct: float = Field(ge=0,le=100)

class LineMetric(Contract):
    line_id: str
    negative_to_positive: int = Field(ge=0)
    positive_to_negative: int = Field(ge=0)

class TrafficSnapshot(Contract):
    schema_version: Literal[1]=1
    source_id: str
    intersection_code: str
    session_id: UUID
    tracking_epoch: UUID
    analytics_epoch: UUID
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Literal["validation_only","authorized_candidate"]
    frame_sequence: int = Field(ge=1)
    received_at: AwareDatetime
    window_started_at: AwareDatetime
    observed_batches: int = Field(ge=1)
    skipped_frames: int = Field(ge=0)
    discontinuities: int = Field(ge=0)
    tentative_visible: int = Field(ge=0,le=100)
    lost_private: int = Field(ge=0,le=200)
    quality: Literal["initializing","limited_sampling","experimental"]
    regions: tuple[RegionMetric,...]
    lines: tuple[LineMetric,...]
    operationally_validated: Literal[False]=False
