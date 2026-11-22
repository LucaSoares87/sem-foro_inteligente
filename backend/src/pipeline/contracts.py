from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from src.ingestion.contracts import Observation

StageName = Literal["inference", "tracking", "analytics", "decision", "reporting"]

class StageValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    state: Literal["completed", "unavailable"]
    synthetic_vehicle_count: int | None = Field(default=None, ge=0, le=10000)

class StageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: StageName
    state: Literal["completed", "unavailable", "skipped", "failed", "circuit_open"]
    attempts: int = Field(ge=0, le=2)
    elapsed_ms: float = Field(ge=0)
    reason: Literal["not_implemented", "dependency_unavailable", "processor_error",
                    "processor_timeout", "transient_exhausted", "circuit_open"] | None = None
    value: StageValue | None = None

class PipelineReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    observation: Observation
    stages: tuple[StageResult, ...]
    state: Literal["completed", "degraded"]
    decision: Literal["abstain"] = "abstain"
    reason: Literal["inference_not_available"] = "inference_not_available"
    finished_at: AwareDatetime

class PipelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sequence: int = Field(ge=1)
    event_id: UUID
    intersection_code: str
    origin: Literal["synthetic"] = "synthetic"
    kind: Literal["started", "stage_finished", "finished", "cancelled"]
    stage: StageName | None = None
    state: str | None = None
    timestamp: AwareDatetime
