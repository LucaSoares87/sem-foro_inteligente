import argparse
import json
import os
from pathlib import Path
from src.validation.contracts import (
    CalibrationChecklist,DatasetManifest,EvaluationRequest,EvaluationThresholds,
    GroundTruth,Predictions,calibration_assessment
)
from src.validation.engine import evaluate
from src.validation.io import canonical_json,load_json_model,verify_video

def _write(path,value):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+".tmp")
    temp.write_text(canonical_json(value),encoding="utf-8")
    os.chmod(temp,0o600)
    temp.replace(target)

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
    _write(args.output,payload)
    print(json.dumps({
        "dataset_id":result.dataset_id,"origin":result.origin,
        "meets_supplied_thresholds":result.meets_supplied_thresholds,
        "result_sha256":result.result_sha256,"output":str(args.output)
    },sort_keys=True))
    return 0 if result.meets_supplied_thresholds else 3

def calibration_command(args):
    checklist=load_json_model(args.input,CalibrationChecklist)
    result=calibration_assessment(checklist)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["state"]=="ready" else 4

def main(argv=None):
    parser=argparse.ArgumentParser(prog="si-validation")
    sub=parser.add_subparsers(dest="command",required=True)
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
    args=parser.parse_args(argv)
    return args.handler(args)

if __name__=="__main__":
    raise SystemExit(main())
