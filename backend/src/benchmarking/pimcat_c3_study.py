"""Actual offline YOLOX person benchmark; aggregate outputs only."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from statistics import fmean
import cv2
from src.archive.store import fingerprint
from src.benchmarking.pimcat_c3_vision import PersonDetector, Perception, Person, iou
from src.validation.io import sha256_file
from src.vision.model_artifacts import YOLOX_S_SHA256

FPS=(30,15,10,5)
FRAMES=240
COMMON=tuple(range(1,FRAMES+1,6))


def blank_reference(pixel_hash):
    return {"status":"DRAFT_NOT_REFERENCE","pixel_sha256":pixel_hash,"model_sha256":YOLOX_S_SHA256,
        "annotator_ref":None,"frames":[{"frame":i,"reviewed":False,"boxes":None} for i in COMMON]}


def independent_metrics(predictions,a,b,reviewer,pixel_hash):
    """Private in-memory evaluation, exact agreement or reviewed replacement needed.
    Does not authenticate reviewer identity or prove independence."""
    if not isinstance(reviewer,str) or not reviewer.strip():return None
    for ref in (a,b):
        if (ref.get("status")!="REVIEWED" or ref.get("pixel_sha256")!=pixel_hash
            or ref.get("model_sha256")!=YOLOX_S_SHA256):return None
        if not isinstance(ref.get("annotator_ref"),str) or not ref["annotator_ref"].strip():return None
        if [x.get("frame") for x in ref.get("frames",[])]!=list(COMMON):return None
        if any(x.get("reviewed") is not True or not isinstance(x.get("boxes"),list) for x in ref["frames"]):return None
    if len({a["annotator_ref"],b["annotator_ref"],reviewer})!=3 or a["frames"]!=b["frames"]:return None
    if set(predictions)!=set(COMMON):return None
    tp=fp=fn=0
    for row in a["frames"]:
        truth=[Person(tuple(x),1) for x in row["boxes"]]
        pred=[x for x in predictions[row["frame"]] if x.score>=.25]
        pairs=sorted(((iou(p.box,g.box),i,j) for i,p in enumerate(pred) for j,g in enumerate(truth)),reverse=True)
        usedp=set();usedg=set()
        for overlap,i,j in pairs:
            if overlap<.5:break
            if i not in usedp and j not in usedg:usedp.add(i);usedg.add(j)
        tp+=len(usedp);fp+=len(pred)-len(usedp);fn+=len(truth)-len(usedg)
    if tp+fn==0:return None
    return {"tp":tp,"fp":fp,"fn":fn,"precision":tp/(tp+fp) if tp+fp else None,
        "recall":tp/(tp+fn),"f1":2*tp/(2*tp+fp+fn),"independence_authenticated":False}


def percentile(x):
    import math
    return sorted(x)[math.ceil(.95*len(x))-1]


def run(video,model,preflight,references=None):
    import hashlib
    if preflight["frames"]!=FRAMES or preflight["fps"]!=30 or preflight["derived_sha256"]!=sha256_file(video):
        raise ValueError("preflight mismatch")
    det=PersonDetector(model)
    cap=cv2.VideoCapture(str(video));pixels=hashlib.sha256()
    cache={};latency={}
    try:
        for i in range(1,FRAMES+1):
            ok,image=cap.read()
            if not ok or image.shape!=(720,1280,3):raise ValueError("missing frame")
            pixels.update(image.tobytes())
            start=perf_counter();cache[i]=det.infer(image);latency[i]=(perf_counter()-start)*1000
        assert not cap.read()[0]
    finally:cap.release()
    assert pixels.hexdigest()==preflight["decoded_pixel_sha256"]
    results={}
    for fps in FPS:
        track=Perception();ids=range(1,FRAMES+1,30//fps);times=[];counts=[];low=0
        for i in ids:
            start=perf_counter();track.update((i-1)/30,cache[i]);times.append((perf_counter()-start)*1000)
            counts.append(sum(p.score>=.25 for p in cache[i]))
            low+=sum(p.score<.25 for p in cache[i])
        times_det=[latency[i] for i in ids]
        results[str(fps)]={"sampled_frames":len(counts),"person_detections":sum(counts),
            "frames_with_person":sum(c>0 for c in counts),"mean_persons_per_sample":fmean(counts),
            "low_confidence_candidates":low,"inference_mean_ms":fmean(times_det),
            "inference_p95_ms":percentile(times_det),"serial_capacity_fps_estimate":1000/fmean(times_det),
            "association_p95_ms":percentile(times),"tracks_created":track.created,
            "tracks_expired":track.expired,"ambiguous_associations":track.ambiguous}
    metrics=None
    if references is not None:
        a,b,reviewer=references
        metrics=independent_metrics({i:cache[i] for i in COMMON},a,b,reviewer,pixels.hexdigest())
        if metrics is None:
            raise ValueError("independent reference incomplete, inconsistent or no positive truth")
    return {"scope":"external_real_replay_scene_detection_not_field","model_sha256":YOLOX_S_SHA256,
        "pixel_sha256":pixels.hexdigest(),"native_inferences":len(cache),"cpu_threads":1,"fps_results":results,
        "reference_frames":len(COMMON),"accuracy_metrics":metrics,
        "precision_state":"METRICS_AVAILABLE_NOT_FIELD_APPROVAL" if metrics is not None else "BLOCKED_BY_INDEPENDENT_ANNOTATION",
        "real_waiting_occupancy_intention":"NOT_RUN_NO_REVIEWED_GEOMETRY",
        "tracking_accuracy":"NOT_RUN","sustained_fps_measured":False,
        "operational_decision":"abstain","physical_actuation":False,"candidate_promoted":False,
        "operationally_validated":False,"commercial_demo_authorized":False}


def main():
    p=argparse.ArgumentParser();p.add_argument("--video",required=True);p.add_argument("--model",required=True)
    p.add_argument("--preflight",required=True);p.add_argument("--output",required=True)
    p.add_argument("--annotation-a");p.add_argument("--annotation-b");p.add_argument("--reviewer-ref")
    a=p.parse_args()
    inputs=(a.annotation_a,a.annotation_b,a.reviewer_ref)
    if any(inputs) and not all(inputs):p.error("all three private reference arguments required")
    references=(json.loads(Path(a.annotation_a).read_text()),json.loads(Path(a.annotation_b).read_text()),a.reviewer_ref) if all(inputs) else None
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    pre=json.loads(Path(a.preflight).read_text())
    if references is None:
        for n in ("annotation-a.json","annotation-b.json"):
            with (root/n).open("x") as f:json.dump(blank_reference(pre["decoded_pixel_sha256"]),f,indent=2)
    report=run(a.video,a.model,pre,references);report["result_sha256"]=fingerprint(report)
    with (root/"study.json").open("x") as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)


if __name__=="__main__":main()
