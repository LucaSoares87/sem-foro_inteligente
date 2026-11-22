from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

class Observation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    event_id: UUID
    intersection_code: str = Field(pattern=r"^[A-Z0-9_-]{2,80}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{2,80}$")
    sequence: int = Field(strict=True, ge=0, le=2**63-1)
    captured_at: AwareDatetime
    origin: Literal["synthetic"] = "synthetic"
    vehicle_count: int = Field(strict=True, ge=0, le=10000)

    @field_validator("captured_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

class Receipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observation: Observation
    state: Literal["queued", "processing", "processed", "failed", "cancelled"]
    accepted_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    processing_ms: float | None = None
    error_code: Literal["processor_error", "processor_timeout", "shutdown"] | None = None

class Handoff(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observation: Observation
    decision: Literal["abstain"] = "abstain"
    reason: Literal["inference_not_available"] = "inference_not_available"
