import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from src.analytics.contracts import SourceGeometry
from src.benchmarking.bellevue import prepare_bellevue_manifest
from src.benchmarking.contracts import FpsBenchmarkCriteria
from src.benchmarking.runner import run_fps_sweep
from src.validation.contracts import (
    CalibrationChecklist,DatasetManifest,EvaluationRequest,EvaluationThresholds,
    GroundTruth,Predictions,calibration_assessment
)
from src.validation.engine import evaluate
from src.validation.io import canonical_json,inspect_video,load_json_model,sha256_file,verify_video
from src.validation.runner import run_case
from src.vision.contracts import ModelSpec

def _atomic_write(path,text):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+".tmp")
    temp.write_text(text,encoding="utf-8")
    os.chmod(temp,0o600)
    temp.replace(target)

def _write_model(path,model):
    _atomic_write(path,model.model_dump_json(indent=2)+"\n")
    return sha256_file(path)

def _write_artifact(path,value):
    payload=dict(value)
    payload["artifact_sha256"]=hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    _atomic_write(path,canonical_json(payload))
    return payload["artifact_sha256"]

def inspect_command(args):
    result=inspect_video(args.video)
    artifact=_write_artifact(args.output,result)
    print(json.dumps({"output":args.output,"artifact_sha256":artifact,
                      "video_sha256":result["sha256"],"frame_count":result["frame_count"]},sort_keys=True))
    return 0

def run_case_command(args):
    manifest=load_json_model(args.manifest,DatasetManifest)
    spec=load_json_model(args.model_spec,ModelSpec)
    geometry=load_json_model(args.geometry,SourceGeometry)
    predictions=asyncio.run(run_case(manifest,args.video,spec,args.model_root,geometry))
    file_sha=_write_model(args.output,predictions)
    print(json.dumps({"dataset_id":predictions.dataset_id,"output":args.output,
                      "predictions_file_sha256":file_sha,
                      "detections":len(predictions.detections),"tracks":len(predictions.tracks)},sort_keys=True))
    return 0

def evaluate_command(args):
    manifest=load_json_model(args.manifest,DatasetManifest)
    truth=load_json_model(args.ground_truth,GroundTruth)
    predictions=load_json_model(args.predictions,Predictions)
    thresholds=load_json_model(args.thresholds,EvaluationThresholds)
    video=verify_video(manifest,args.video)
    request=EvaluationRequest(manifest=manifest,ground_truth=truth,predictions=predictions,
                              thresholds=thresholds,iou_threshold=args.iou)
    result=evaluate(request)
    payload={"video_verification":video,"evaluation":result.model_dump(mode="json")}
    artifact=_write_artifact(args.output,payload)
    print(json.dumps({
        "dataset_id":result.dataset_id,"origin":result.origin,
        "meets_supplied_thresholds":result.meets_supplied_thresholds,
        "result_sha256":result.result_sha256,"artifact_sha256":artifact,"output":str(args.output)
    },sort_keys=True))
    return 0 if result.meets_supplied_thresholds else 3

def calibration_command(args):
    checklist=load_json_model(args.input,CalibrationChecklist)
    result=calibration_assessment(checklist)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["state"]=="ready" else 4

def prepare_bellevue_command(args):
    manifest=prepare_bellevue_manifest(args.video,args.dataset_id,args.source_id,
        args.intersection_code,args.recorded_at)
    file_sha=_write_model(args.output,manifest)
    print(json.dumps({
        "dataset_id":manifest.dataset_id,"output":args.output,
        "manifest_file_sha256":file_sha,"video_sha256":manifest.video_sha256,
        "commercial_demo_authorized":manifest.commercial_demo_authorized
    },sort_keys=True))
    return 0

def fps_sweep_command(args):
    manifest=load_json_model(args.manifest,DatasetManifest)
    spec=load_json_model(args.model_spec,ModelSpec)
    geometry=load_json_model(args.geometry,SourceGeometry)
    criteria=load_json_model(args.criteria,FpsBenchmarkCriteria)
    report=asyncio.run(run_fps_sweep(manifest,args.video,spec,args.model_root,geometry,criteria))
    file_sha=_write_model(args.output,report)
    print(json.dumps({
        "dataset_id":report.dataset_id,"output":args.output,
        "benchmark_file_sha256":file_sha,
        "recommended_min_fps":report.engineering_recommended_min_fps,
        "commercial_demo_authorized":report.commercial_demo_authorized,
        "operationally_validated":report.operationally_validated
    },sort_keys=True))
    return 0

def main(argv=None):
    parser=argparse.ArgumentParser(prog="si-validation")
    sub=parser.add_subparsers(dest="command",required=True)

    inspect=sub.add_parser("inspect-video")
    inspect.add_argument("--video",required=True)
    inspect.add_argument("--output",required=True)
    inspect.set_defaults(handler=inspect_command)

    run=sub.add_parser("run-case")
    run.add_argument("--manifest",required=True)
    run.add_argument("--video",required=True)
    run.add_argument("--model-spec",required=True)
    run.add_argument("--model-root",required=True)
    run.add_argument("--geometry",required=True)
    run.add_argument("--output",required=True)
    run.set_defaults(handler=run_case_command)

    ev=sub.add_parser("evaluate")
    ev.add_argument("--manifest",required=True)
    ev.add_argument("--ground-truth",required=True)
    ev.add_argument("--predictions",required=True)
    ev.add_argument("--thresholds",required=True)
    ev.add_argument("--video",required=True)
    ev.add_argument("--output",required=True)
    ev.add_argument("--iou",type=float,default=.5)
    ev.set_defaults(handler=evaluate_command)

    cal=sub.add_parser("calibration")
    cal.add_argument("--input",required=True)
    cal.set_defaults(handler=calibration_command)

    prep=sub.add_parser("prepare-bellevue")
    prep.add_argument("--video",required=True)
    prep.add_argument("--dataset-id",required=True)
    prep.add_argument("--source-id",required=True)
    prep.add_argument("--intersection-code",required=True)
    prep.add_argument("--recorded-at")
    prep.add_argument("--output",required=True)
    prep.set_defaults(handler=prepare_bellevue_command)

    fps=sub.add_parser("fps-sweep")
    fps.add_argument("--manifest",required=True)
    fps.add_argument("--video",required=True)
    fps.add_argument("--model-spec",required=True)
    fps.add_argument("--model-root",required=True)
    fps.add_argument("--geometry",required=True)
    fps.add_argument("--criteria",required=True)
    fps.add_argument("--output",required=True)
    fps.set_defaults(handler=fps_sweep_command)

    args=parser.parse_args(argv)
    return args.handler(args)

if __name__=="__main__":
    raise SystemExit(main())
