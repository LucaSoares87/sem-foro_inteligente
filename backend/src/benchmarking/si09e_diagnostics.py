"""Offline paired research replay. No change to production tracker, geometry or confidence."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime,timedelta,timezone
import json
import math
from pathlib import Path
from statistics import fmean
from time import perf_counter
from uuid import uuid4

import cv2

from src.analytics.contracts import SourceGeometry
from src.analytics.engine import TrafficEngine
from src.archive.store import fingerprint
from src.benchmarking.runner import _should_sample, _source_spec
from src.optimization.engine import evaluate
from src.queueing.engine import QueueEstimator
from src.tracking.tracker import ByteTrackInspired
from src.validation.contracts import DatasetManifest
from src.validation.io import load_json_model, verify_video
from src.video.contracts import MAX_JPEG
from src.vision.contracts import Detection, DetectionBatch, ModelSpec
from src.vision.service import InferenceWorker

RATES=(30,15,10,5)


def temporal_geometry(geometry, fps):
    if fps not in RATES:
        raise ValueError("unsupported diagnostic rate")
    # Same physical-time limit at every rate; existing seconds limit remains binding.
    return SourceGeometry.model_validate({**geometry.model_dump(),
        "max_gap_frames":min(30,max(1,math.ceil(geometry.max_gap_seconds*fps)))})


async def collect(manifest,video,spec,root,worker_factory=InferenceWorker):
    verify_video(manifest,video)
    if manifest.origin!="external_real_replay" or manifest.commercial_demo_authorized or spec.purpose!="validation_only":
        raise ValueError("research-only input required")
    if manifest.fps!=30 or manifest.frame_count!=960:
        raise ValueError("paired diagnostic requires exact SI-09D 32-second clip")
    capture=cv2.VideoCapture(str(video))
    worker=worker_factory(spec,root)
    rows=[]
    try:
        if not capture.isOpened():
            raise ValueError("video not decodable")
        await worker.open()
        for i in range(manifest.frame_count):
            ok,frame=capture.read()
            if not ok or frame is None or frame.shape[:2]!=(manifest.height,manifest.width):
                raise ValueError("unexpected frame or resolution")
            ok,jpeg=cv2.imencode(".jpg",frame,[int(cv2.IMWRITE_JPEG_QUALITY),90])
            if not ok or not 0<len(jpeg)<=MAX_JPEG:
                raise ValueError("invalid jpeg")
            result=await worker.infer(jpeg.tobytes())
            ms=float(result["inference_ms"])
            if not math.isfinite(ms) or ms<0:
                raise ValueError("invalid inference latency")
            rows.append((tuple(Detection.model_validate(d) for d in result["detections"]),ms))
    finally:
        capture.release()
        await worker.close()
    return rows


def replay(manifest,spec,geometry,rows,fps):
    if fps not in RATES or len(rows)!=manifest.frame_count:
        raise ValueError("invalid paired input")
    if any(a.visibility_calibrated for a in geometry.approaches):
        raise ValueError("preliminary geometry must remain uncalibrated")
    if (manifest.source_id,manifest.intersection_code)!=(geometry.source_id,geometry.intersection_code):
        raise ValueError("geometry mismatch")
    if not geometry.approaches:
        raise ValueError("approaches required")
    tracker=ByteTrackInspired(high=max(.6,spec.confidence),low=spec.confidence)
    configs={"baseline":geometry,"temporal_candidate":temporal_geometry(geometry,fps)}
    engines={k:TrafficEngine(g) for k,g in configs.items()}
    queues={k:QueueEstimator(g) for k,g in configs.items()}
    source=_source_spec(manifest,fps)
    session=uuid4()
    ids=set()
    counts=Counter()
    samples={k:[] for k in configs}
    final={}
    states={k:{} for k in configs}
    seq=0
    last=-1
    latency=[]
    tracking=[]
    start=perf_counter()
    for i,(detections,ms) in enumerate(rows,1):
        sample,slot=_should_sample(i,manifest.fps,fps,last)
        if not sample:
            continue
        last=slot
        seq+=1
        batch=DetectionBatch(source_id=manifest.source_id,intersection_code=manifest.intersection_code,
            session_id=session,frame_sequence=seq,received_at=manifest.recorded_at+timedelta(seconds=(i-1)/manifest.fps),
            inferred_at=datetime.now(timezone.utc),model_sha256=spec.sha256,purpose=spec.purpose,
            inference_ms=ms,detections=detections)
        track=tracker.update(batch)
        latency.append(ms)
        tracking.append(track.tracking_ms)
        counts["detections"]+=len(detections)
        counts["tentative_observations"]+=sum(t.state=="tentative" for t in track.tracks)
        counts["confirmed_observations"]+=sum(t.state=="confirmed" for t in track.tracks)
        counts["lost_track_observations"]+=track.lost_private
        ids.update(t.track_id for t in track.tracks if t.state=="confirmed")
        for name,engine in engines.items():
            analytics=engine.consume(track)
            queue=queues[name].consume(track,analytics,source)
            opt=evaluate(queue)
            if opt.preferred_in_simulation!="abstain" or opt.dynamic_x_safe_vehicles is not None or opt.physical_actuation:
                raise ValueError("uncalibrated replay must abstain")
            samples[name].extend(a.observation_confidence for a in queue.approaches)
            states[name][int((i-1)/manifest.fps)]={a.approach_id:a.queue_length for a in queue.approaches}
            final[name]=analytics
    variants={}
    for name,g in configs.items():
        snap=final[name]
        variants[name]={"geometry_sha256":snap.geometry_sha256,"max_gap_frames":g.max_gap_frames,
            "max_gap_seconds":g.max_gap_seconds,"line_counts":[l.model_dump(mode="json") for l in snap.lines],
            "queue_by_second":states[name],"mean_confidence":fmean(samples[name]),
            "decision_state":"abstain","x":None,"discontinuities":snap.discontinuities}
    return {"fps":fps,"frames":seq,"unique_confirmed_track_ids":len(ids),
        "track_ids_are_not_vehicle_counts":True,**dict(counts),
        "cached_inference_mean_ms":fmean(latency),"tracking_mean_ms":fmean(tracking),
        "paired_replay_wall_seconds":perf_counter()-start,"variants":variants}


async def main_async(args):
    manifest=load_json_model(args.manifest,DatasetManifest)
    spec=load_json_model(args.model_spec,ModelSpec)
    geometry=load_json_model(args.geometry,SourceGeometry)
    rows=await collect(manifest,args.video,spec,args.model_root)
    cache_digest=fingerprint([{"source_frame":i,"detections":[d.model_dump(mode="json") for d in ds]}
        for i,(ds,_) in enumerate(rows,1)])
    result={"schema_version":1,"scope":"paired_diagnostic_not_accuracy","origin":manifest.origin,
        "video_sha256":manifest.video_sha256,"model_sha256":spec.sha256,
        "detection_cache_sha256":cache_digest,"unique_inferences":len(rows),
        "runs":[replay(manifest,spec,geometry,rows,fps) for fps in RATES],
        "ground_truth_state":"pending_independent_annotation","calibration_state":"blocked",
        "candidate_promoted":False,"engineering_recommended_min_fps":None,
        "commercial_demo_authorized":False,"operationally_validated":False,"physical_actuation":False}
    result["result_sha256"]=fingerprint(result)
    output=Path(args.output)
    with output.open("x",encoding="utf-8") as handle:
        json.dump(result,handle,sort_keys=True,indent=2)
    print(json.dumps({"unique_inferences":len(rows),"result_sha256":result["result_sha256"]}))


def main():
    p=argparse.ArgumentParser()
    for name in ("manifest","video","model-spec","model-root","geometry","output"):
        p.add_argument("--"+name,required=True)
    asyncio.run(main_async(p.parse_args()))


if __name__=="__main__":
    main()
