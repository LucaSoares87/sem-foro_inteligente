"""Research reference for the exact paired replay; absent annotations are never zeros."""
import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Literal

from pydantic import Field,model_validator

from src.analytics.contracts import Contract,SourceGeometry
from src.analytics.engine import TrafficEngine
from src.archive.store import fingerprint
from src.validation.contracts import CountValue
from src.validation.io import load_json_model

SHA=r"^[0-9a-f]{64}$"
Direction=Literal["negative_to_positive","positive_to_negative"]


class QueueLabel(Contract):
    second:int=Field(ge=0,le=31)
    approach_id:str
    count:int=Field(ge=0)


class IndependentReference(Contract):
    schema_version:Literal[1]=1
    scope:Literal["bellevue_si09d_32s_research"]="bellevue_si09d_32s_research"
    video_sha256:str=Field(pattern=SHA)
    geometry_sha256:str=Field(pattern=SHA)
    status:Literal["draft","reviewed"]
    annotation_method:Literal["manual_visual_without_model_predictions"]
    annotator_reference:str=Field(min_length=1,max_length=160)
    independent_reviewer_reference:str|None=Field(default=None,max_length=160)
    full_passage_coverage:bool=False
    counts:tuple[CountValue,...]=()
    queues:tuple[QueueLabel,...]=()

    @model_validator(mode="after")
    def validate_entries(self):
        keys=[(x.line_id,x.direction) for x in self.counts]
        if len(set(keys))!=len(keys) or any(x.label is not None for x in self.counts):
            raise ValueError("aggregate direction counts must be unique")
        qkeys=[(x.second,x.approach_id) for x in self.queues]
        if len(set(qkeys))!=len(qkeys):
            raise ValueError("duplicate queue label")
        if self.status=="reviewed" and (not self.independent_reviewer_reference
                or self.independent_reviewer_reference==self.annotator_reference
                or not self.full_passage_coverage):
            raise ValueError("independent reviewer and full passage coverage required")
        return self


def compare_reference(reference,report,geometry):
    if report.get("scope")!="paired_diagnostic_not_accuracy":
        raise ValueError("paired diagnostic report required")
    geometry_hash=TrafficEngine(geometry).geometry_hash
    if reference.video_sha256!=report["video_sha256"] or reference.geometry_sha256!=geometry_hash:
        raise ValueError("reference identity mismatch")
    expected={(line.line_id,d) for line in geometry.lines for d in ("negative_to_positive","positive_to_negative")}
    approaches={a.approach_id for a in geometry.approaches}
    expected_queue={(s,a) for s in range(32) for a in approaches}
    actual={(c.line_id,c.direction):c.count for c in reference.counts}
    queue={(q.second,q.approach_id):q.count for q in reference.queues}
    if not set(actual)<=expected or not set(queue)<=expected_queue:
        raise ValueError("reference contains unknown geometry")
    base={"reference_sha256":fingerprint(reference.model_dump(mode="json")),
        "report_sha256":report["result_sha256"],"geometry_sha256":geometry_hash,
        "missing_count_keys":len(expected-set(actual)),"missing_queue_keys":len(expected_queue-set(queue)),
        "operationally_validated":False,"physical_actuation":False,"candidate_promoted":False}
    if reference.status!="reviewed" or set(actual)!=expected or set(queue)!=expected_queue:
        return {**base,"state":"BLOCKED_BY_INDEPENDENT_REFERENCE","metrics":None}
    rows=[]
    for run in report["runs"]:
        for name,variant in run["variants"].items():
            pred={(line["line_id"],d):line[d] for line in variant["line_counts"]
                for d in ("negative_to_positive","positive_to_negative")}
            pq={(int(s),a):v for s,groups in variant["queue_by_second"].items() for a,v in groups.items()}
            if set(pred)!=expected or set(pq)!=expected_queue:
                raise ValueError("prediction coverage mismatch")
            error=sum(abs(pred[k]-actual[k]) for k in expected)
            total=sum(actual.values())
            rows.append({"fps":run["fps"],"variant":name,"count_absolute_error":error,
                "count_relative_error":error/total if total else None,
                "truth_total":total,"queue_mae_vehicles":fmean(abs(pq[k]-queue[k]) for k in expected_queue),
                "scope":"research_reviewed_reference_not_field_acceptance"})
    return {**base,"state":"REFERENCE_COMPARISON_COMPLETE","metrics":rows}


def main():
    p=argparse.ArgumentParser()
    for name in ("reference","report","geometry","output"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    ref=load_json_model(a.reference,IndependentReference)
    geo=load_json_model(a.geometry,SourceGeometry)
    report=json.loads(Path(a.report).read_text())
    body=dict(report)
    sha=body.pop("result_sha256",None)
    if sha!=fingerprint(body):
        raise ValueError("paired report hash mismatch")
    result=compare_reference(ref,report,geo)
    with Path(a.output).open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,sort_keys=True)


if __name__=="__main__":
    main()
