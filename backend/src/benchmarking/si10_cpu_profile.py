"""Research-only CPU microbenchmark; production detector and scheduling unchanged."""
import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
from statistics import fmean, median
from time import perf_counter

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from src.archive.store import fingerprint
from src.benchmarking.si09f_validation import HOLDOUTS, write_new
from src.validation.io import sha256_file, load_json_model
from src.vision.contracts import ModelSpec, MAX_JPEG
from src.vision.model_artifacts import YOLOX_S_SHA256
from src.vision.yolo import YoloDetector

PIXELS = {
    "morning_0708":"267517689ef40643aea26ce7af6b5a489a2509d7608b742cf1aa2913885c86a8",
    "morning_1108":"59defab79d8e3cff84e29458ba6d9df5565a6b8c8564697672f530aac7bc3530",
}
# One real frame each second, fixed before timing. Not a continuous tracking replay.
INDICES = tuple(1 + 30*i for i in range(32))
SCORE_TOL = 1e-4
BOX_TOL = 1e-4


def read_frames(case, source):
    name, digest=HOLDOUTS[case]
    source=Path(source)
    if source.name!=name or sha256_file(source)!=digest:
        raise ValueError("official source identity mismatch")
    capture=cv2.VideoCapture(str(source))
    pixels=hashlib.sha256()
    samples=[]
    stamps=[]
    try:
        if not capture.isOpened():
            raise ValueError("source not decodable")
        for i in range(961):
            ok,frame=capture.read()
            if not ok or frame.shape!=(720,1280,3):
                raise ValueError("source decode or resolution mismatch")
            if i==0:
                continue
            stamp=capture.get(cv2.CAP_PROP_POS_MSEC)/1000
            if not math.isfinite(stamp) or stamp<0:
                raise ValueError("invalid source timestamp")
            if stamps and (abs(stamp-stamps[-1]-1/30)>.002 or abs(stamp-stamps[0]-len(stamps)/30)>.002):
                raise ValueError("source cadence mismatch")
            stamps.append(stamp)
            pixels.update(frame.tobytes())
            if i in INDICES:
                samples.append(frame.copy())
    finally:
        capture.release()
    if pixels.hexdigest()!=PIXELS[case] or len(samples)!=32:
        raise ValueError("frozen holdout pixel hash mismatch")
    return samples


def parity(reference, candidate):
    """Order-independent class/count parity, one-to-one bounded box and score match."""
    if len(reference)!=len(candidate):
        return False
    if not reference:
        return True
    costs=np.full((len(reference),len(candidate)),1e9)
    for i,a in enumerate(reference):
        for j,b in enumerate(candidate):
            if a.label==b.label:
                box=max(abs(x-y) for x,y in zip(a.xyxy,b.xyxy))
                score=abs(a.confidence-b.confidence)
                if box<=BOX_TOL and score<=SCORE_TOL:
                    costs[i,j]=box+score
    ri,ci=linear_sum_assignment(costs)
    return bool(np.all(costs[ri,ci]<1e9))


def p95(values):
    return sorted(values)[math.ceil(.95*len(values))-1]


def cpu_budget():
    logical=os.cpu_count() or 1
    affinity=len(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else logical
    quota=None
    try:
        raw,period=Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if raw!="max":
            quota=int(raw)/int(period)
    except (OSError,ValueError,ZeroDivisionError):
        pass
    budget=min(logical,affinity,max(1,math.floor(quota)) if quota is not None else affinity)
    return {"logical_cpus":logical,"affinity_cpus":affinity,"quota_cpus":quota,
            "thread_budget":budget,"opencv_version":cv2.__version__,"platform":platform.platform()}


def profile(samples,spec,root):
    if spec.sha256!=YOLOX_S_SHA256 or spec.purpose!="validation_only" or spec.architecture!="yolox":
        raise ValueError("pinned research model required")
    if len(samples)!=32:
        raise ValueError("fixed sample set required")
    hw=cpu_budget()
    threads=[n for n in (1,2,4) if n<=hw["thread_budget"]]
    order=threads+list(reversed(threads))
    old=cv2.getNumThreads()
    detector=None
    runs=[]
    baseline=None
    try:
        detector=YoloDetector(spec.resolve(root),spec)
        for trial,n in enumerate(order,1):
            cv2.setNumThreads(n)
            if cv2.getNumThreads()!=n:
                raise ValueError("OpenCV thread setting not applied")
            for frame in samples[:3]:
                detector.infer(frame)
            all_dets=[]
            e2e=[]
            inference=[]
            jpeg_times=[]
            for frame in samples:
                start=perf_counter()
                ok,jpeg=cv2.imencode(".jpg",frame,[int(cv2.IMWRITE_JPEG_QUALITY),90])
                if not ok or not 0<len(jpeg)<=MAX_JPEG:
                    raise ValueError("invalid JPEG")
                image=cv2.imdecode(jpeg,cv2.IMREAD_COLOR)
                if image is None or image.shape!=frame.shape:
                    raise ValueError("JPEG decode mismatch")
                mid=perf_counter()
                ds=detector.infer(image)
                end=perf_counter()
                all_dets.append(ds)
                jpeg_times.append((mid-start)*1000)
                inference.append((end-mid)*1000)
                e2e.append((end-start)*1000)
            if baseline is None:
                baseline=all_dets
            matches=sum(parity(a,b) for a,b in zip(baseline,all_dets))
            runs.append({"trial":trial,"threads":n,"frames":len(samples),
                "mean_ms":fmean(e2e),"median_ms":median(e2e),"p95_ms":p95(e2e),
                "jpeg_mean_ms":fmean(jpeg_times),"detector_mean_ms":fmean(inference),
                "sequential_sample_fps":1000/fmean(e2e),"parity_frames":matches,
                "all_frames_match_baseline":matches==len(samples)})
    finally:
        cv2.setNumThreads(old)
    by_threads=[]
    for n in threads:
        rs=[r for r in runs if r["threads"]==n]
        by_threads.append({"threads":n,"median_trial_mean_ms":median([r["mean_ms"] for r in rs]),
            "worst_trial_p95_ms":max(r["p95_ms"] for r in rs),
            "all_trials_parity":all(r["all_frames_match_baseline"] for r in rs)})
    return hw,runs,by_threads


def main():
    p=argparse.ArgumentParser()
    for arg in ("case","source","model-spec","model-root","output"):
        p.add_argument("--"+arg,required=True)
    a=p.parse_args()
    if a.case not in HOLDOUTS:
        raise ValueError("unknown holdout")
    spec=load_json_model(a.model_spec,ModelSpec)
    samples=read_frames(a.case,a.source)
    hw,runs,summary=profile(samples,spec,a.model_root)
    result={"schema_version":1,"case":a.case,"scope":"offline_cpu_microbenchmark_not_live",
        "source_sha256":HOLDOUTS[a.case][1],"decoded_pixel_sha256":PIXELS[a.case],
        "model_sha256":spec.sha256,"sample_indices_zero_based_source":list(INDICES),
        "hardware":hw,"runs":runs,"summary":summary,
        "score_tolerance":SCORE_TOL,"normalized_box_tolerance":BOX_TOL,
        "candidate_promoted":False,"engineering_recommended_min_fps":None,
        "ground_truth_validated":False,"commercial_demo_authorized":False,
        "operationally_validated":False,"physical_actuation":False}
    result["result_sha256"]=fingerprint(result)
    write_new(a.output,result)


if __name__=="__main__":
    main()
