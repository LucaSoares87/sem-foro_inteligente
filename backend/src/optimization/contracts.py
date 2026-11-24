from typing import Literal
from pydantic import Field
from src.analytics.contracts import Contract

class ServiceGroupState(Contract):
    group_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    queue_length: int = Field(ge=0,le=400)
    arrival_rate_vps: float = Field(ge=0,le=40)
    discharge_rate_vps: float = Field(ge=0,le=40)
    mean_wait_seconds: float = Field(ge=0,le=86400)
    max_wait_seconds: float = Field(ge=0,le=86400)
    storage_capacity_vehicles: int = Field(ge=1,le=400)
    storage_occupancy_ratio: float = Field(ge=0,le=2)
    observation_confidence: float = Field(ge=0,le=1)

class CandidateMetrics(Contract):
    sequence: Literal["minor_first","major_first"]
    queue_area_vehicle_seconds: float = Field(ge=0)
    peak_combined_queue: float = Field(ge=0)
    spillback_exposure_vehicle_seconds: float = Field(ge=0)
    max_wait_proxy_seconds: float = Field(ge=0)
    flow_interruption_proxy: float = Field(ge=0)
    transition_overhead_seconds: float = Field(ge=0)
    analysis_first_window_seconds: float = Field(ge=0)
    total_cost: float = Field(ge=0)

class OptimizationResult(Contract):
    schema_version: Literal[1]=1
    algorithm: Literal["dynamic_clear_first_v1"]="dynamic_clear_first_v1"
    cost_model: Literal["continuity_queue_cost_v1"]="continuity_queue_cost_v1"
    origin: Literal["observed","external_real_replay","synthetic_demo"]
    source_id: str
    intersection_code: str
    frame_sequence: int = Field(ge=1)
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["simulation_preference","abstain"]
    reason: Literal[
        "minor_first_lower_cost","major_first_lower_cost","no_material_advantage",
        "insufficient_observation_confidence","requires_two_service_groups",
        "no_net_minor_clearance","minor_exceeds_dynamic_x"
    ]
    major_group: ServiceGroupState | None = None
    minor_group: ServiceGroupState | None = None
    dynamic_x_safe_vehicles: int | None = Field(default=None,ge=0,le=400)
    minor_clearance_seconds: float | None = Field(default=None,ge=0)
    minor_clearance_feasible: bool = False
    preferred_in_simulation: Literal["minor_first","major_first","no_material_advantage","abstain"]
    material_gain_pct: float | None = None
    minor_first: CandidateMetrics | None = None
    major_first: CandidateMetrics | None = None
    horizon_seconds: int = Field(default=60,ge=1)
    critical_storage_ratio: float = Field(default=.85,ge=.5,le=1)
    minimum_confidence: float = Field(default=.65,ge=0,le=1)
    engineering_weights_validated: Literal[False]=False
    operationally_validated: Literal[False]=False
    physical_actuation: Literal[False]=False
    operational_decision: Literal["abstain"]="abstain"
