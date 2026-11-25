"""Prepare and inspect private field inputs; never generate or register gate evidence."""
import argparse
import json
from pathlib import Path
from src.analytics.contracts import SourceGeometry
from src.validation.contracts import (CalibrationChecklist, DatasetManifest, GroundTruth,
    EvaluationThresholds, Predictions, EvidenceRecord, PILOT_REQUIRED, calibration_assessment)
from src.validation.io import load_json_model, inspect_video, sha256_file
from src.vision.contracts import ModelSpec

SCHEMAS={"manifest":DatasetManifest,"ground-truth":GroundTruth,"thresholds":EvaluationThresholds,
    "calibration":CalibrationChecklist,"geometry":SourceGeometry,"model-spec":ModelSpec,
    "predictions":Predictions,"evidence-record":EvidenceRecord}
REFERENCES=("capture_authorization_ref","model_authorization_ref","operator_ref","annotator_ref",
    "independent_reviewer_ref","threshold_approval_ref","hardware_ref","recovery_approval_ref")


def write_new(path,data):
    with Path(path).open("x",encoding="utf-8") as f:
        json.dump(data,f,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)
        f.write("\n")


def prepare(root):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=False)
    for name,model in SCHEMAS.items():
        write_new(root/(name+".schema.json"),model.model_json_schema())
    write_new(root/"field-dossier.draft.json",{
        "status":"DRAFT_NOT_FIELD_EVIDENCE","references":dict.fromkeys(REFERENCES),
        "reviewed_frames":None,"ground_truth_sha256":None,
        "geometry_sha256":None,"model_sha256":None,"video_sha256":None,
        "thresholds_sha256":None,"human_acceptance_ref":None,
        "pilot_ready":False,"physical_actuation":False})
    write_new(root/"gate-plan.json",{"scope":"field_preparation_only",
        "gates":{g:"pending_human" if g=="human_acceptance" else "not_run" if g in
            ("hardware_benchmark","recovery_drill") else "blocked" for g in sorted(PILOT_REQUIRED)},
        "pilot_ready":False,"operational_decision":"abstain","physical_actuation":False})
    # Deliberately invalid placeholders cannot be consumed as a ground truth or approved threshold.
    (root/"README.txt").write_text(
        "Schemas are contracts, not field artifacts. Complete actual manifest.json, ground-truth.json, "
        "thresholds.json, calibration.json, geometry.json, model-spec.json and field-dossier.json privately. "
        "Review every frame independently, including explicit zero-object frames. Record aggregate counts "
        "in both directions for every line; unknown is not zero. No automatic gate registration.\n",
        encoding="utf-8")


def coverage(truth,manifest,geometry,reviewed):
    # Review metadata declares complete coverage; the declaration still requires human verification.
    if not isinstance(reviewed,list) or len(reviewed)!=manifest.frame_count or any(type(x)is not int for x in reviewed):
        raise ValueError("incomplete explicit frame review")
    if sorted(reviewed)!=list(range(1,manifest.frame_count+1)):
        raise ValueError("duplicate or missing reviewed frame")
    if truth.dataset_id!=manifest.dataset_id or not truth.annotations:
        raise ValueError("representative annotated traffic required; blank truth is not zero traffic")
    if any(a.frame_sequence>manifest.frame_count or a.label not in manifest.classes for a in truth.annotations):
        raise ValueError("annotation outside manifest")
    expected={(line.line_id,d,None) for line in geometry.lines for d in ("negative_to_positive","positive_to_negative")}
    actual={(c.line_id,c.direction,c.label) for c in truth.counts}
    if not expected or actual!=expected:
        raise ValueError("complete aggregate count reference required")


def inspect(root,video,model_root):
    root=Path(root)
    dossier=json.loads((root/"field-dossier.json").read_text(encoding="utf-8"))
    refs=dossier.get("references",{})
    if dossier.get("status")!="SUBMITTED_FOR_REVIEW" or any(not isinstance(refs.get(k),str) or not refs[k].strip() for k in REFERENCES):
        raise ValueError("missing external references")
    if len({refs[k].strip() for k in ("operator_ref","annotator_ref","independent_reviewer_ref")})!=3:
        raise ValueError("separate operator, annotator and reviewer references required")
    loaded={n:load_json_model(root/(n+".json"),SCHEMAS[n]) for n in
            ("manifest","ground-truth","thresholds","calibration","geometry","model-spec")}
    m,t,th,cal,g,s=(loaded[n] for n in ("manifest","ground-truth","thresholds","calibration","geometry","model-spec"))
    if m.origin!="field" or s.purpose!="authorized_candidate" or th.purpose!="field_acceptance":
        raise ValueError("field inputs and authorized candidate designation required")
    if m.authorization_ref!=refs["capture_authorization_ref"] or th.approval_reference!=refs["threshold_approval_ref"]:
        raise ValueError("authorization reference mismatch")
    if th.approved_at>m.recorded_at:
        raise ValueError("thresholds approved after capture")
    if (m.source_id,m.intersection_code)!=(g.source_id,g.intersection_code) or (m.source_id,m.intersection_code)!=(cal.source_id,cal.intersection_code):
        raise ValueError("scene identity mismatch")
    if calibration_assessment(cal)["state"]!="ready" or not g.approaches or not all(a.visibility_calibrated for a in g.approaches):
        raise ValueError("calibration incomplete")
    coverage(t,m,g,dossier.get("reviewed_frames"))
    actual=inspect_video(video)
    for k,v in (("filename",m.video_filename),("sha256",m.video_sha256),("width",m.width),("height",m.height),("frame_count",m.frame_count)):
        if actual[k]!=v:
            raise ValueError("video identity mismatch: "+k)
    if abs(actual["fps"]-m.fps)>.001:
        raise ValueError("video fps mismatch")
    hashes={"ground_truth_sha256":sha256_file(root/"ground-truth.json"),"geometry_sha256":sha256_file(root/"geometry.json"),
        "thresholds_sha256":sha256_file(root/"thresholds.json"),"video_sha256":actual["sha256"],
        "model_sha256":sha256_file(s.resolve(model_root))}
    if hashes["model_sha256"]!=s.sha256 or any(dossier.get(k)!=v for k,v in hashes.items()):
        raise ValueError("artifact identity mismatch")
    return {"scope":"private_field_input_consistency_only","state":"INPUTS_CONSISTENT_PENDING_EXECUTION_AND_HUMAN_REVIEW",
        "hashes":hashes,"reviewed_frame_count":m.frame_count,"annotation_count":len(t.annotations),
        "count_keys":len(t.counts),"independence_authenticated":False,"pilot_ready":False,
        "physical_actuation":False,"operational_decision":"abstain"}


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("prepare");a.add_argument("--directory",required=True)
    a=sub.add_parser("inspect");a.add_argument("--directory",required=True);a.add_argument("--video",required=True)
    a.add_argument("--model-root",required=True);a.add_argument("--output",required=True)
    args=p.parse_args()
    if args.command=="prepare":
        prepare(args.directory)
    else:
        write_new(args.output,inspect(args.directory,args.video,args.model_root))


if __name__=="__main__":
    main()
