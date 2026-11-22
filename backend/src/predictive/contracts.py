from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field
from src.analytics.contracts import Contract, LineMetric

class RegionAggregate(Contract):
    region_id: str
    mean_visible: float = Field(ge=0,le=100)
    peak_visible: int = Field(ge=0,le=100)
    mean_image_coverage_pct: float = Field(ge=0,le=100)

class TrafficWindow(Contract):
    schema_version: Literal[1]=1
    source_id: str
    intersection_code: str
    analytics_epoch: UUID
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Literal["validation_only","authorized_candidate"]
    start_sequence: int = Field(ge=1)
    end_sequence: int = Field(ge=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    duration_seconds: float = Field(ge=60,le=62)
    sampled_intervals: int = Field(ge=1)
    skipped_frames: int = Field(ge=0)
    limited_intervals: int = Field(ge=0)
    regions: tuple[RegionAggregate,...]
    lines: tuple[LineMetric,...]
    operationally_validated: Literal[False]=False
