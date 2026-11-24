"""Offline research only. Never converts incomplete annotation into truth."""
import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from src.analytics.contracts import Contract, SourceGeometry
from src.analytics.engine import TrafficEngine
from src.archive.store import fingerprint
from src.benchmarking.bellevue import prepare_bellevue_manifest
from src.benchmarking.si09d_preflight import prepare
from src.benchmarking.si09e_reference import IndependentReference, QueueLabel, compare_reference
from src.validation.contracts import CountValue
from src.validation.io import load_json_model, sha256_file

HOLDOUTS = {
    "morning_0708": ("Bellevue_116th_NE12th__2017-09-11_07-08-32.mp4",
                     "4dde510ff91c2ec58e1cd06e27cbd923d8976c0156905a4625097653415eca4e"),
    "morning_1108": ("Bellevue_116th_NE12th__2017-09-11_11-08-33.mp4",
                     "6cc98923b4c4cef029b352b9346819efa607b23041cc0e6a5f35dcb8980351fd"),
}
DIRECTIONS = ("negative_to_positive", "positive_to_negative")
SHA = r"^[0-9a-f]{64}$"
SECONDS = 32


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def expected_keys(geometry):
    return ({(line.line_id, d) for line in geometry.lines for d in DIRECTIONS},
            {(s, a.approach_id) for s in range(SECONDS) for a in geometry.approaches})


class Annotation(Contract):
    schema_version: Literal[1] = 1
    case_id: Literal["morning_0708", "morning_1108"]
    video_sha256: str = Field(pattern=SHA)
    geometry_sha256: str = Field(pattern=SHA)
    decoded_pixel_sha256: str = Field(pattern=SHA)
    annotation_method: Literal["manual_visual_without_model_predictions"]
    annotator_reference: str = Field(min_length=1, max_length=160)
    status: Literal["draft", "submitted"] = "draft"
    full_passage_coverage: bool = False
    counts: tuple[CountValue, ...] = ()
    queues: tuple[QueueLabel, ...] = ()

    @model_validator(mode="after")
    def unique_keys(self):
        c = [(x.line_id, x.direction) for x in self.counts]
        q = [(x.second, x.approach_id) for x in self.queues]
        if len(set(c)) != len(c) or len(set(q)) != len(q) or any(x.label is not None for x in self.counts):
            raise ValueError("duplicate or non-aggregate reference labels")
        if self.status == "submitted" and (self.annotator_reference.strip().lower() in {"", "pending"} or not self.full_passage_coverage):
            raise ValueError("submitted annotation requires identified annotator and coverage")
        return self


class Review(Contract):
    reviewer_reference: str = Field(min_length=1, max_length=160)
    annotation_a_sha256: str = Field(pattern=SHA)
    annotation_b_sha256: str = Field(pattern=SHA)
    accepted: bool = False


def prepare_case(case, source, video, geometry, output):
    if case not in HOLDOUTS:
        raise ValueError("unknown holdout")
    name, sha = HOLDOUTS[case]
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    if any((root/n).exists() for n in ("preflight.json", "manifest.json", "annotation-packet.json")):
        raise ValueError("refusing to overwrite research evidence")
    evidence = prepare(source, video, SECONDS, source_name=name, source_sha=sha)
    if evidence["frames"] != 960 or evidence["source_start_frame_zero_based"] != 1:
        raise ValueError("holdout differs from registered span")
    manifest = prepare_bellevue_manifest(video, "bellevue-si09f-"+case,
        geometry.source_id, geometry.intersection_code, evidence["recorded_at"])
    if manifest.video_sha256 != evidence["derived_sha256"]:
        raise ValueError("prepared video hash mismatch")
    write_new(root/"preflight.json", evidence)
    write_new(root/"manifest.json", manifest.model_dump(mode="json"))
    geo_sha = TrafficEngine(geometry).geometry_hash
    counts, queues = expected_keys(geometry)
    if not counts or not queues or any(a.visibility_calibrated for a in geometry.approaches):
        raise ValueError("unreviewed geometry required")
    blank = {"case_id":case, "video_sha256":manifest.video_sha256,
             "decoded_pixel_sha256":evidence["decoded_pixel_sha256"],"geometry_sha256":geo_sha,
             "annotation_method":"manual_visual_without_model_predictions","annotator_reference":"pending",
             "status":"draft","full_passage_coverage":False,"counts":[],"queues":[]}
    packet = {"scope":"blinded_research_annotation","case_id":case,"source_sha256":sha,
        "source_start_frame_zero_based":evidence["source_start_frame_zero_based"],
        "source_end_frame_exclusive":evidence["source_end_frame_exclusive"],
        "reference_template":blank,"geometry":geometry.model_dump(mode="json"),
        "required_count_keys":[{"line_id":l,"direction":d} for l,d in sorted(counts)],
        "required_queue_keys":[{"second":s,"approach_id":a,"native_frame_one_based":30*(s+1)} for s,a in sorted(queues)],
        "calibration_state":"PENDING_INDEPENDENT_GEOMETRY_REVIEW",
        "commercial_demo_authorized":False,"operationally_validated":False,"physical_actuation":False}
    write_new(root/"annotation-packet.json",packet)
    return packet


def gate(case, preflight, geometry, report, a, b, review=None):
    if case not in HOLDOUTS or preflight["source_sha256"] != HOLDOUTS[case][1]:
        raise ValueError("holdout source mismatch")
    if (preflight["frames"],preflight["fps"],preflight["source_start_frame_zero_based"]) != (960,30,1):
        raise ValueError("holdout span mismatch")
    body = dict(report)
    digest = body.pop("result_sha256",None)
    if digest != fingerprint(body) or report.get("scope") != "paired_diagnostic_not_accuracy":
        raise ValueError("invalid paired report hash or scope")
    if report["video_sha256"] != preflight["derived_sha256"] or report.get("unique_inferences") != 960:
        raise ValueError("paired report not bound to prepared holdout")
    if [x["fps"] for x in report["runs"]] != [30,15,10,5] or [x["frames"] for x in report["runs"]] != [960,480,320,160]:
        raise ValueError("unexpected sampling schedule")
    geo_sha = TrafficEngine(geometry).geometry_hash
    expected_c, expected_q = expected_keys(geometry)
    for run in report["runs"]:
        if set(run["variants"]) != {"baseline","temporal_candidate"}:
            raise ValueError("paired variants missing")
        for variant in run["variants"].values():
            if variant["decision_state"]!="abstain" or variant["x"] is not None:
                raise ValueError("uncalibrated candidate must abstain")
            pcounts={(l["line_id"],d) for l in variant["line_counts"] for d in DIRECTIONS}
            pqueues={(int(s),k) for s,groups in variant["queue_by_second"].items() for k in groups}
            if pcounts!=expected_c or pqueues!=expected_q:
                raise ValueError("paired report coverage mismatch")
        if run["variants"]["baseline"]["geometry_sha256"]!=geo_sha:
            raise ValueError("baseline geometry mismatch")
    mappings=[]
    hashes=[]
    for ann in (a,b):
        if (ann.case_id,ann.video_sha256,ann.geometry_sha256,ann.decoded_pixel_sha256)!=(
            case,preflight["derived_sha256"],geo_sha,preflight["decoded_pixel_sha256"]):
            raise ValueError("annotation identity mismatch")
        c={(x.line_id,x.direction):x.count for x in ann.counts}
        q={(x.second,x.approach_id):x.count for x in ann.queues}
        if not set(c)<=expected_c or not set(q)<=expected_q:
            raise ValueError("unknown annotation key")
        mappings.append((c,q))
        hashes.append(fingerprint(ann.model_dump(mode="json")))
    (ac,aq),(bc,bq)=mappings
    disagreements={"counts":sum(ac[k]!=bc[k] for k in set(ac)&set(bc)),
                   "queues":sum(aq[k]!=bq[k] for k in set(aq)&set(bq))}
    result={"case_id":case,"report_sha256":digest,"annotation_sha256":hashes,
        "missing_keys_a":len(expected_c-set(ac))+len(expected_q-set(aq)),
        "missing_keys_b":len(expected_c-set(bc))+len(expected_q-set(bq)),
        "disagreements":disagreements,"accuracy_metrics":None,
        "calibration_state":"PENDING_INDEPENDENT_GEOMETRY_REVIEW","candidate_promoted":False,
        "engineering_recommended_min_fps":None,"commercial_demo_authorized":False,
        "operationally_validated":False,"physical_actuation":False}
    if result["missing_keys_a"] or result["missing_keys_b"] or a.status!="submitted" or b.status!="submitted":
        return {**result,"state":"BLOCKED_BY_INDEPENDENT_ANNOTATION"}
    refs={a.annotator_reference.strip().casefold(),b.annotator_reference.strip().casefold()}
    if len(refs)!=2:
        raise ValueError("independent annotators must differ")
    if any(disagreements.values()):
        return {**result,"state":"BLOCKED_BY_ANNOTATION_DISAGREEMENT"}
    if not review or not review.accepted:
        return {**result,"state":"PENDING_INDEPENDENT_REVIEW"}
    reviewer=review.reviewer_reference.strip().casefold()
    if reviewer in refs|{"","pending"} or (review.annotation_a_sha256,review.annotation_b_sha256)!=tuple(hashes):
        raise ValueError("independent review identity or hash mismatch")
    ref=IndependentReference(video_sha256=a.video_sha256,geometry_sha256=geo_sha,
        status="reviewed",annotation_method=a.annotation_method,annotator_reference=a.annotator_reference,
        independent_reviewer_reference=review.reviewer_reference,full_passage_coverage=True,
        counts=a.counts,queues=a.queues)
    evaluated=compare_reference(ref,report,geometry)
    metrics=evaluated["metrics"]
    for metric in metrics:
        count_ok=(metric["count_absolute_error"]==0 if metric["truth_total"]==0
                  else metric["count_relative_error"]<=.05)
        metric["meets_proposed_count_queue_thresholds"]=count_ok and metric["queue_mae_vehicles"]<=1
    return {**result,"state":"REVIEWED_RESEARCH_COMPARISON","accuracy_metrics":metrics}


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    prep=sub.add_parser("prepare")
    for key in ("case","source","video","geometry","output"):
        prep.add_argument("--"+key,required=True)
    check=sub.add_parser("gate")
    for key in ("case","preflight","geometry","report","annotation-a","annotation-b","output"):
        check.add_argument("--"+key,required=True)
    check.add_argument("--review")
    args=p.parse_args()
    geo=load_json_model(args.geometry,SourceGeometry)
    if args.command=="prepare":
        prepare_case(args.case,args.source,args.video,geo,args.output)
    else:
        preflight=json.loads(Path(args.preflight).read_text())
        report=json.loads(Path(args.report).read_text())
        a=load_json_model(args.annotation_a,Annotation)
        b=load_json_model(args.annotation_b,Annotation)
        review=load_json_model(args.review,Review) if args.review else None
        write_new(args.output,gate(args.case,preflight,geo,report,a,b,review))


if __name__=="__main__":
    main()
