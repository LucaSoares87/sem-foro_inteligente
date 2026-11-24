from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field
from src.analytics.contracts import Contract

class QueueApproachState(Contract):
    approach_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    service_group: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    visible_vehicles: int = Field(ge=0,le=200)
    queue_length: int = Field(ge=0,le=200)
    stopped_ratio: float = Field(ge=0,le=1)
    arrival_rate_vps: float = Field(ge=0,le=20)
    discharge_rate_vps: float = Field(ge=0,le=20)
    queue_growth_vps: float = Field(ge=-20,le=20)
    mean_wait_seconds: float = Field(ge=0,le=86400)
    max_wait_seconds: float = Field(ge=0,le=86400)
    storage_capacity_vehicles: int = Field(ge=1,le=200)
    storage_occupancy_ratio: float = Field(ge=0,le=2)
    spillback_margin_ratio: float = Field(ge=0,le=1)
    observation_confidence: float = Field(ge=0,le=1)
    visibility_calibrated: bool
    quality: Literal["initializing","limited_sampling","experimental"]
    speed_basis: Literal["normalized_image_motion"]="normalized_image_motion"

class QueueSnapshot(Contract):
    schema_version: Literal[1]=1
    algorithm: Literal["queue_estimator_v1"]="queue_estimator_v1"
    source_id: str
    intersection_code: str
    session_id: UUID
    tracking_epoch: UUID
    analytics_epoch: UUID
    queue_epoch: UUID
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Literal["validation_only","authorized_candidate"]
    data_origin: Literal["local_authorized","external_real_replay","synthetic_demo"]
    commercial_demo_authorized: bool
    frame_sequence: int = Field(ge=1)
    received_at: AwareDatetime
    approaches: tuple[QueueApproachState,...]
    physical_speed_available: Literal[False]=False
    operationally_validated: Literal[False]=False
    physical_actuation: Literal[False]=False
