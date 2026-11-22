from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator
from src.ingestion.contracts import Receipt
from src.pipeline.contracts import PipelineEvent, PipelineReport

class ArchivedRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    receipt: Receipt
    report: PipelineReport
    events: tuple[PipelineEvent, ...]

    @model_validator(mode="after")
    def verify_correlation(self):
        observation = self.report.observation
        if self.receipt.observation != observation or self.receipt.state != "processed":
            raise ValueError("invalid receipt")
        if self.receipt.finished_at is None:
            raise ValueError("missing finish timestamp")
        if len(self.events) != 7 or self.events[0].kind != "started" or self.events[-1].kind != "finished":
            raise ValueError("incomplete journal")
        if any(e.event_id != observation.event_id or e.intersection_code != observation.intersection_code
               for e in self.events):
            raise ValueError("invalid event correlation")
        if any(b.sequence != a.sequence + 1 for a,b in zip(self.events,self.events[1:])):
            raise ValueError("noncontiguous journal")
        if len(self.report.stages) != 5 or self.events[-1].state != self.report.state:
            raise ValueError("invalid stage report")
        for event, stage in zip(self.events[1:-1], self.report.stages):
            if event.kind != "stage_finished" or event.stage != stage.stage or event.state != stage.state:
                raise ValueError("stage mismatch")
        return self
