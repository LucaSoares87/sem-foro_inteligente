from datetime import datetime,timedelta,timezone
from pathlib import Path
from statistics import fmean
from uuid import uuid4
import cv2

from src.analytics.engine import TrafficEngine
from src.archive.store import fingerprint
from src.benchmarking.contracts import (
    FpsApproachObservation,FpsBenchmarkReport,FpsComparison,FpsRunSummary,FpsSecondObservation
)
from src.optimization.engine import evaluate as optimize
from src.queueing.engine import QueueEstimator
from src.tracking.tracker import ByteTrackInspired
from src.validation.contracts import CountValue
from src.validation.io import verify_video
from src.video.contracts import MAX_JPEG,SourceSpec
from src.vision.contracts import DetectionBatch
from src.vision.service import InferenceWorker

def _percentile(values,p):
    if not values:
        return 0.0
    ordered=sorted(values)
    index=min(len(ordered)-1,max(0,int(round((len(ordered)-1)*p))))
    return ordered[index]

def _source_spec(manifest,target_fps):
    origin={"external_real_replay":"external_real_replay",
            "synthetic":"synthetic_demo","field":"local_authorized"}[manifest.origin]
    return SourceSpec(source_id=manifest.source_id,intersection_code=manifest.intersection_code,
        kind="file",locator=manifest.video_filename,target_fps=target_fps,
        data_origin=origin,commercial_demo_authorized=manifest.commercial_demo_authorized,
        authorization_ref=manifest.authorization_ref)

def _should_sample(frame_index,source_fps,target_fps,last_slot):
    slot=int(((frame_index-1)*target_fps/source_fps)+1e-9)
    return slot>last_slot,slot

def _counts(snapshot):
    if snapshot is None:
        return ()
    values=[]
    for line in snapshot.lines:
        values.append(CountValue(line_id=line.line_id,direction="negative_to_positive",
                                 label=None,count=line.negative_to_positive))
        values.append(CountValue(line_id=line.line_id,direction="positive_to_negative",
                                 label=None,count=line.positive_to_negative))
    return tuple(values)

def _second_state(second,queue_snapshot,result):
    approaches=tuple(FpsApproachObservation(
        approach_id=item.approach_id,queue_length=item.queue_length,
        arrival_rate_vps=item.arrival_rate_vps,discharge_rate_vps=item.discharge_rate_vps,
        mean_wait_seconds=item.mean_wait_seconds,
        observation_confidence=item.observation_confidence)
        for item in sorted(queue_snapshot.approaches,key=lambda value:value.approach_id))
    return FpsSecondObservation(second=second,approaches=approaches,
        dynamic_x_safe_vehicles=result.dynamic_x_safe_vehicles if result else None,
        preferred_in_simulation=result.preferred_in_simulation if result else "abstain",
        optimization_state=result.state if result else "abstain")

async def run_rate(manifest,video_path,spec,model_root,geometry,target_fps,
                   worker_factory=InferenceWorker,capture_factory=cv2.VideoCapture):
    if not geometry.approaches:
        raise ValueError("queue approaches required for fps benchmark")
    if target_fps>manifest.fps+.5:
        raise ValueError("target fps exceeds source fps")
    capture=capture_factory(str(Path(video_path)))
    if not capture.isOpened():
        raise ValueError("video not decodable")
    worker=worker_factory(spec,model_root)
    tracker=ByteTrackInspired(high=max(.6,spec.confidence),low=spec.confidence)
    traffic=TrafficEngine(geometry)
    queue=QueueEstimator(geometry)
    source_spec=_source_spec(manifest,target_fps)
    session_id=uuid4()
    source_frames=processed=detections=confirmed=0
    last_slot=-1
    inference_ms=[]
    tracking_ms=[]
    confidence=[]
    states={}
    last_traffic=None
    await worker.open()
    try:
        while source_frames<manifest.frame_count:
            source_frames+=1
            sample,slot=_should_sample(source_frames,manifest.fps,target_fps,last_slot)
            if hasattr(capture,"grab") and hasattr(capture,"retrieve"):
                if not capture.grab():
                    raise ValueError("video ended before manifest frame count")
                if not sample:
                    continue
                ok,frame=capture.retrieve()
            else:
                ok,frame=capture.read()
                if not ok or frame is None:
                    raise ValueError("video ended before manifest frame count")
                if not sample:
                    continue
            if not ok or frame is None:
                raise ValueError("sampled frame decode failed")
            last_slot=slot
            processed+=1
            if frame.shape[1]!=manifest.width or frame.shape[0]!=manifest.height:
                raise ValueError("frame resolution drift")
            encoded,jpeg=cv2.imencode(".jpg",frame,[int(cv2.IMWRITE_JPEG_QUALITY),90])
            if not encoded:
                raise ValueError("frame jpeg encoding failed")
            raw=jpeg.tobytes()
            if not 0<len(raw)<=MAX_JPEG:
                raise ValueError("encoded frame exceeds inference transport limit")
            result=await worker.infer(raw)
            received=manifest.recorded_at+timedelta(seconds=(source_frames-1)/manifest.fps)
            detection=DetectionBatch(source_id=manifest.source_id,
                intersection_code=manifest.intersection_code,session_id=session_id,
                frame_sequence=processed,received_at=received,inferred_at=datetime.now(timezone.utc),
                model_sha256=spec.sha256,purpose=spec.purpose,inference_ms=result["inference_ms"],
                detections=result["detections"])
            tracked=tracker.update(detection)
            analytics=traffic.consume(tracked)
            queue_snapshot=queue.consume(tracked,analytics,source_spec)
            optimization=optimize(queue_snapshot)
            inference_ms.append(detection.inference_ms)
            tracking_ms.append(tracked.tracking_ms)
            detections+=len(detection.detections)
            confirmed+=sum(item.state=="confirmed" for item in tracked.tracks)
            confidence.extend(item.observation_confidence for item in queue_snapshot.approaches)
            second=int((received-manifest.recorded_at).total_seconds())
            states[second]=_second_state(second,queue_snapshot,optimization)
            last_traffic=analytics
    finally:
        capture.release()
        await worker.close()
    if processed<1:
        raise ValueError("fps benchmark produced no samples")
    return FpsRunSummary(target_fps=target_fps,source_fps=manifest.fps,
        source_frames_seen=source_frames,processed_frames=processed,
        duration_seconds=manifest.frame_count/manifest.fps,
        inference_mean_ms=fmean(inference_ms),inference_p95_ms=_percentile(inference_ms,.95),
        tracking_mean_ms=fmean(tracking_ms),detections_total=detections,
        confirmed_track_observations=confirmed,final_counts=_counts(last_traffic),
        seconds=tuple(states[key] for key in sorted(states)),
        mean_observation_confidence=fmean(confidence) if confidence else 0.0)

def _count_map(run):
    return {(item.line_id,item.direction,item.label):item.count for item in run.final_counts}

def compare_runs(reference,target,criteria):
    ref_seconds={item.second:item for item in reference.seconds}
    target_seconds={item.second:item for item in target.seconds}
    common=sorted(set(ref_seconds)&set(target_seconds))
    queue_errors=[]
    arrival_errors=[]
    discharge_errors=[]
    x_errors=[]
    preference_pairs=[]
    for second in common:
        left,right=ref_seconds[second],target_seconds[second]
        la={item.approach_id:item for item in left.approaches}
        ra={item.approach_id:item for item in right.approaches}
        for approach_id in sorted(set(la)&set(ra)):
            queue_errors.append(abs(la[approach_id].queue_length-ra[approach_id].queue_length))
            arrival_errors.append(abs(la[approach_id].arrival_rate_vps-ra[approach_id].arrival_rate_vps))
            discharge_errors.append(abs(la[approach_id].discharge_rate_vps-ra[approach_id].discharge_rate_vps))
        if left.dynamic_x_safe_vehicles is not None and right.dynamic_x_safe_vehicles is not None:
            x_errors.append(abs(left.dynamic_x_safe_vehicles-right.dynamic_x_safe_vehicles))
        if left.preferred_in_simulation!="abstain" and right.preferred_in_simulation!="abstain":
            preference_pairs.append(left.preferred_in_simulation==right.preferred_in_simulation)
    ref_counts=_count_map(reference)
    target_counts=_count_map(target)
    keys=set(ref_counts)|set(target_counts)
    absolute=sum(abs(ref_counts.get(key,0)-target_counts.get(key,0)) for key in keys)
    ref_total=sum(ref_counts.values())
    count_error=(0.0 if absolute==0 else 1.0) if ref_total==0 else min(1.0,absolute/ref_total)
    queue_mae=fmean(queue_errors) if queue_errors else None
    arrival_mae=fmean(arrival_errors) if arrival_errors else None
    discharge_mae=fmean(discharge_errors) if discharge_errors else None
    x_mae=fmean(x_errors) if x_errors else None
    agreement=(sum(preference_pairs)/len(preference_pairs)) if preference_pairs else None
    meets=(len(common)>=criteria.min_common_seconds and
           len(preference_pairs)>=criteria.min_decision_seconds and
           len(x_errors)>=criteria.min_x_seconds and
           queue_mae is not None and queue_mae<=criteria.max_queue_mae_vehicles and
           count_error<=criteria.max_count_relative_error and
           x_mae is not None and x_mae<=criteria.max_x_mae_vehicles and
           agreement is not None and agreement>=criteria.min_preference_agreement)
    return FpsComparison(target_fps=target.target_fps,reference_fps=reference.target_fps,
        common_seconds=len(common),decision_comparable_seconds=len(preference_pairs),
        x_comparable_seconds=len(x_errors),queue_mae_vehicles=queue_mae,
        arrival_rate_mae_vps=arrival_mae,discharge_rate_mae_vps=discharge_mae,
        x_mae_vehicles=x_mae,preference_agreement=agreement,
        final_count_relative_error=count_error,meets_engineering_stability_criteria=meets)

async def run_fps_sweep(manifest,video_path,spec,model_root,geometry,criteria,
                        worker_factory=InferenceWorker,capture_factory=cv2.VideoCapture,verify=verify_video):
    verify(manifest,video_path)
    if criteria.approved_at>datetime.now(timezone.utc):
        raise ValueError("benchmark criteria must be approved before execution")
    if (geometry.source_id,geometry.intersection_code)!=(manifest.source_id,manifest.intersection_code):
        raise ValueError("geometry/manifest mismatch")
    runs=[]
    for target in criteria.target_fps:
        runs.append(await run_rate(manifest,video_path,spec,model_root,geometry,target,
            worker_factory=worker_factory,capture_factory=capture_factory))
    by_fps={run.target_fps:run for run in runs}
    reference=by_fps[criteria.reference_fps]
    comparisons=tuple(compare_runs(reference,run,criteria) for run in runs
                      if run.target_fps!=criteria.reference_fps)
    passing=[criteria.reference_fps]+[item.target_fps for item in comparisons
                                      if item.meets_engineering_stability_criteria]
    geometry_hash=TrafficEngine(geometry).geometry_hash
    criteria_sha=fingerprint(criteria.model_dump(mode="json"))
    body={"schema_version":1,"benchmark":"bellevue_fps_sweep_v1",
          "dataset_id":manifest.dataset_id,"origin":manifest.origin,
          "video_sha256":manifest.video_sha256,"model_sha256":spec.sha256,
          "geometry_sha256":geometry_hash,"criteria_sha256":criteria_sha,
          "commercial_demo_authorized":manifest.commercial_demo_authorized,
          "runs":[run.model_dump(mode="json") for run in runs],
          "comparisons":[item.model_dump(mode="json") for item in comparisons],
          "engineering_recommended_min_fps":min(passing),
          "benchmark_complete":True,"operationally_validated":False,"physical_actuation":False}
    body["result_sha256"]=fingerprint(body)
    return FpsBenchmarkReport.model_validate(body)
