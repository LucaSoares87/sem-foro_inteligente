from typing import Literal
from pydantic import AwareDatetime,Field,model_validator
from src.analytics.contracts import Contract
from src.validation.contracts import CountValue

class FpsBenchmarkCriteria(Contract):
    schema_version: Literal[1]=1
    purpose: Literal["engineering_bellevue_replay"]="engineering_bellevue_replay"
    approval_reference: str = Field(min_length=2,max_length=240)
    approved_at: AwareDatetime
    reference_fps: int = Field(default=30,strict=True,ge=1,le=30)
    target_fps: tuple[int,...] = Field(default=(30,15,10,5),min_length=2,max_length=8)
    max_queue_mae_vehicles: float = Field(default=1.0,ge=0,le=20)
    max_count_relative_error: float = Field(default=.05,ge=0,le=1)
    max_x_mae_vehicles: float = Field(default=1.0,ge=0,le=20)
    min_preference_agreement: float = Field(default=.95,ge=0,le=1)
    min_common_seconds: int = Field(default=30,ge=1,le=3600)
    min_decision_seconds: int = Field(default=10,ge=1,le=3600)
    min_x_seconds: int = Field(default=5,ge=1,le=3600)

    @model_validator(mode="after")
    def validate_rates(self):
        if len(set(self.target_fps))!=len(self.target_fps):
            raise ValueError("duplicate target fps")
        if self.reference_fps not in self.target_fps:
            raise ValueError("reference fps must be included")
        if tuple(sorted(self.target_fps,reverse=True))!=self.target_fps:
            raise ValueError("target fps must be descending")
        return self

class FpsApproachObservation(Contract):
    approach_id: str
    queue_length: int = Field(ge=0)
    arrival_rate_vps: float = Field(ge=0)
    discharge_rate_vps: float = Field(ge=0)
    mean_wait_seconds: float = Field(ge=0)
    observation_confidence: float = Field(ge=0,le=1)

class FpsSecondObservation(Contract):
    second: int = Field(ge=0)
    approaches: tuple[FpsApproachObservation,...]
    dynamic_x_safe_vehicles: int | None = Field(default=None,ge=0)
    preferred_in_simulation: Literal["minor_first","major_first","no_material_advantage","abstain"]
    optimization_state: Literal["simulation_preference","abstain"]

class FpsRunSummary(Contract):
    target_fps: int = Field(strict=True,ge=1,le=30)
    source_fps: float = Field(gt=0,le=30)
    source_frames_seen: int = Field(ge=1)
    processed_frames: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    inference_mean_ms: float = Field(ge=0)
    inference_p95_ms: float = Field(ge=0)
    tracking_mean_ms: float = Field(ge=0)
    detections_total: int = Field(ge=0)
    confirmed_track_observations: int = Field(ge=0)
    final_counts: tuple[CountValue,...]
    seconds: tuple[FpsSecondObservation,...]
    mean_observation_confidence: float = Field(ge=0,le=1)

class FpsComparison(Contract):
    target_fps: int = Field(strict=True,ge=1,le=30)
    reference_fps: int = Field(strict=True,ge=1,le=30)
    common_seconds: int = Field(ge=0)
    decision_comparable_seconds: int = Field(ge=0)
    x_comparable_seconds: int = Field(ge=0)
    queue_mae_vehicles: float | None = Field(default=None,ge=0)
    arrival_rate_mae_vps: float | None = Field(default=None,ge=0)
    discharge_rate_mae_vps: float | None = Field(default=None,ge=0)
    x_mae_vehicles: float | None = Field(default=None,ge=0)
    preference_agreement: float | None = Field(default=None,ge=0,le=1)
    final_count_relative_error: float = Field(ge=0,le=1)
    meets_engineering_stability_criteria: bool

class FpsBenchmarkReport(Contract):
    schema_version: Literal[1]=1
    benchmark: Literal["bellevue_fps_sweep_v1"]="bellevue_fps_sweep_v1"
    dataset_id: str
    origin: Literal["external_real_replay","synthetic","field"]
    video_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    criteria_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    commercial_demo_authorized: bool
    runs: tuple[FpsRunSummary,...]
    comparisons: tuple[FpsComparison,...]
    engineering_recommended_min_fps: int | None = Field(default=None,ge=1,le=30)
    benchmark_complete: Literal[True]=True
    operationally_validated: Literal[False]=False
    physical_actuation: Literal[False]=False
