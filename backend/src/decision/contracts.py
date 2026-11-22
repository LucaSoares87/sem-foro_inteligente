from typing import Literal
from pydantic import Field
from src.analytics.contracts import Contract

class CycleDemand(Contract):
    a: int = Field(strict=True,ge=0,le=120)
    b: int = Field(strict=True,ge=0,le=120)

class SimulationScenario(Contract):
    schema_version: Literal[1] = 1
    origin: Literal["synthetic"] = "synthetic"
    cycles: tuple[CycleDemand,...] = Field(min_length=2,max_length=20)
    initial_a: int = Field(default=0,strict=True,ge=0,le=200)
    initial_b: int = Field(default=0,strict=True,ge=0,le=200)

class CycleResult(Contract):
    cycle: int
    service_a_ticks: int
    service_b_ticks: int
    idle_ticks: int
    arrivals_a: int
    arrivals_b: int
    served_a: int
    served_b: int
    end_a: int
    end_b: int
    queue_area: int
    peak_combined: int

class SimulationResult(Contract):
    policy: Literal["fixed","adaptive"]
    cycles: tuple[CycleResult,...]
    arrivals: int
    initial_queue: int
    served: int
    final_queue: int
    queue_area: int
    peak_combined: int
    queue_area_a: int
    queue_area_b: int

class Comparison(Contract):
    schema_version: Literal[1]=1
    algorithm: Literal["abstract_two_queue_v1"]="abstract_two_queue_v1"
    origin: Literal["synthetic"]="synthetic"
    execution_mode: Literal["simulation"]="simulation"
    operationally_validated: Literal[False]=False
    physical_actuation: Literal[False]=False
    scenario_sha256: str
    result_sha256: str
    scenario: SimulationScenario
    fixed: SimulationResult
    adaptive: SimulationResult
    preferred_in_simulation: Literal["fixed","adaptive","equivalent"]
    reason: Literal["lower_queue_area_without_regression","adaptive_tradeoff_or_no_gain","equal_outcomes"]
    queue_area_reduction_pct: float | None
