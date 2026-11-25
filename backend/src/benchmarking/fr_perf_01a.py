"""FR-PERF-01A only: fixed synthetic memory replay, isolated worker, no controller."""
import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import resource
from statistics import median
from time import monotonic, process_time
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
from src.analytics.contracts import SourceGeometry
from src.analytics.service import AnalyticsService
from src.archive.store import fingerprint
from src.benchmarking.fr_perf_01_accounting import DURATION, RATE, OFFERED, coverage, summarize_paced, trial_order
from src.benchmarking.field_integrated_lab import worker_resources
from src.benchmarking.si10_cpu_profile import cpu_budget, parity, read_frames, HOLDOUTS
from src.benchmarking.si10b_shadow_load import ResearchWorker, process_sample
from src.tracking.service import TrackingService
from src.validation.field_readiness import private_path, write
from src.validation.io import load_json_model, sha256_file
from src.video.contracts import SourceSpec, VideoFrame, MAX_JPEG
from src.vision.contracts import Detection, ModelSpec
from src.vision.model_artifacts import YOLOX_S_SHA256
from src.vision.service import VisionService

KEY="FR_PERF_LAB"
WIDTH,HEIGHT=320,240

def encode(image):
    ok,jpeg=cv2.imencode(".jpg",image,[int(cv2.IMWRITE_JPEG_QUALITY),90])
    if not ok or not 0<len(jpeg)<=MAX_JPEG:
        raise ValueError("invalid JPEG")
    return jpeg.tobytes()

def synthetic_frames():
    # Fixed, non-photographic patterns; not a labeled traffic dataset.
    frames=[]
    for k in range(OFFERED):
        image=np.zeros((HEIGHT,WIDTH,3),np.uint8)
        image[:]=[35,65,35]
        cv2.rectangle(image,(0,85),(319,210),(65,65,65),-1)
        for x in range(0,320,40):
            cv2.line(image,(x,147),(min(x+20,319),147),(230,230,230),2)
        x=(3*k)%270
        cv2.rectangle(image,(x,100),(x+45,128),(30,80,220),-1)
        x=270-(2*k)%270
        cv2.rectangle(image,(x,165),(x+45,193),(210,110,40),-1)
        frames.append(encode(image))
    return frames

class Replay:
    def __init__(self):
        spec=SourceSpec(source_id=KEY,intersection_code=KEY,kind="file",locator="synthetic.mp4",
            target_fps=RATE,data_origin="synthetic_demo",commercial_demo_authorized=False)
        self.sessions={KEY:SimpleNamespace(spec=spec,session_id=uuid4(),state="running")}
        self.slot=None;self.offers={};self.taken={};self.overwritten=[];self.start=None
    def publish(self,k,jpeg):
        if k in self.offers or k!=len(self.offers):
            raise ValueError("offer sequence mismatch")
        now=monotonic()-self.start
        self.offers[k]=now
        if self.slot is not None:self.overwritten.append(self.slot.sequence-1)
        s=self.sessions[KEY]
        self.slot=VideoFrame(KEY,KEY,k+1,WIDTH,HEIGHT,datetime.now(timezone.utc),0.,jpeg,s.session_id)
    def take_latest(self,key):
        if key!=KEY:raise ValueError("unknown source")
        frame,self.slot=self.slot,None
        if frame is not None:
            k=frame.sequence-1
            if k in self.taken:raise ValueError("duplicate take")
            self.taken[k]=monotonic()-self.start
        return frame

class MeasuredTracking(TrackingService):
    def __init__(self,vision,replay):
        super().__init__(vision);self.replay=replay;self.completed={}
    def consume(self,batch):
        super().consume(batch)
        snap=self.analytics.latest(KEY)
        k=batch.frame_sequence-1
        if (snap is None or batch.source_id!=KEY or batch.session_id!=self.replay.sessions[KEY].session_id
            or snap.session_id!=batch.session_id or snap.frame_sequence!=batch.frame_sequence
            or snap.model_sha256!=batch.model_sha256 or k not in self.replay.taken or k in self.completed):
            raise ValueError("completion lineage mismatch")
        self.completed[k]=dict(done=monotonic()-self.replay.start,received=self.replay.offers[k],
            inference_ms=batch.inference_ms)

async def run_trial(frames,threads,spec,root):
    replay=Replay();worker=ResearchWorker(spec,root,threads,frames[0])
    vision=VisionService(replay,spec,root,worker_factory=lambda *_:worker)
    track=MeasuredTracking(vision,replay)
    geom=SourceGeometry.model_validate(dict(source_id=KEY,intersection_code=KEY,
        regions=[dict(region_id="lab",xyxy=[.1,.1,.9,.9])],
        lines=[dict(line_id="lab_line",start=[.1,.5],end=[.9,.5])]))
    analytics=AnalyticsService(track,{KEY:geom});vision.tracking=track;track.analytics=analytics
    rows=[];resources=[];producer=None;error=None;elapsed=None;observed=None;cpu=None
    async def produce():
        for k,jpeg in enumerate(frames):
            due=replay.start+k/RATE
            while monotonic()<due:await asyncio.sleep(max(0,due-monotonic()))
            replay.publish(k,jpeg)
    try:
        vision.start()
        async with asyncio.timeout(60):
            while vision.state!="ready":
                if vision.state=="error":raise RuntimeError("warmup_failed")
                await asyncio.sleep(.02)
        replay.start=monotonic();cpu=process_time();next_sample=0.
        producer=asyncio.create_task(produce())
        async with asyncio.timeout(DURATION+15):
            while True:
                now=monotonic()-replay.start
                if vision.state!="ready" or track.failed or analytics.failed:
                    raise RuntimeError("stage_failed")
                if observed is None and (now>=next_sample or now>=DURATION):
                    rows.append(dict(t=now,offered=len(replay.offers),taken=len(replay.taken),
                        vision=vision.processed,tracking=track.processed,analytics=analytics.processed,
                        overwritten=len(replay.overwritten),discarded=vision.discarded))
                    sample=process_sample(worker)
                    if sample is not None:resources.append(sample)
                    next_sample+=1
                    if next_sample<now:next_sample=now+1
                    if now>=DURATION:observed=now
                if producer.done():
                    await producer
                    if observed is not None and replay.slot is None and len(track.completed)==len(replay.taken):
                        break
                await asyncio.sleep(.02)
        elapsed=monotonic()-replay.start
    except Exception as exc:
        error=type(exc).__name__+":"+str(exc)[:160]
        if replay.start is not None:elapsed=monotonic()-replay.start
    finally:
        if producer is not None:
            if not producer.done():producer.cancel()
            await asyncio.gather(producer,return_exceptions=True)
        await vision.shutdown()
    pending=sorted(set(replay.offers)-set(track.completed)-set(replay.overwritten))
    counts=dict(vision=vision.processed,tracking=track.processed,analytics=analytics.processed)
    failures=dict(tracking=track.failed,analytics=analytics.failed)
    cleanup=vision.task is None and worker.process is None and (producer is None or producer.done())
    summary=None
    try:
        # Discarded frame IDs cannot be guessed from aggregate counters. Any such case is invalid.
        if vision.discarded:raise ValueError("unattributed discard")
        summary=summarize_paced(replay.offers,track.completed,replay.overwritten,[],pending)
    except ValueError as exc:
        if error is None:error=str(exc)
    worker_cpu,worker_rss=worker_resources(resources)
    checks=dict(coverage=observed is not None and coverage([r["t"] for r in rows],observed),
        conservation=summary is not None and not pending and len(replay.taken)==len(track.completed)
        and all(v==len(track.completed) for v in counts.values()) and not vision.discarded,
        no_error=error is None and all(v==0 for v in failures.values()),cleanup=cleanup,
        positive_progress=bool(track.completed))
    return dict(threads=threads,elapsed_seconds=elapsed,observation_seconds=observed,
        offers=[dict(slot=k,t=v) for k,v in replay.offers.items()],
        taken=[dict(slot=k,t=v) for k,v in replay.taken.items()],
        completions=[dict(slot=k,**v) for k,v in track.completed.items()],
        overwritten=replay.overwritten,pending=pending,unpublished=sorted(set(range(OFFERED))-set(replay.offers)),
        discarded_count=vision.discarded,rows=rows,worker_samples=resources,
        parent_cpu_seconds=process_time()-cpu if cpu is not None else None,
        parent_process_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        worker_cpu_seconds=worker_cpu,worker_peak_sampled_rss_kib=worker_rss,
        stage_counts=counts,failures=failures,error=error,checks=checks,summary=summary,
        technical_gate=all(checks.values()),capacity_gate=all(checks.values()) and bool(summary and summary["capacity_gate"]))

async def parity_trial(frames,threads,spec,root,reference):
    worker=ResearchWorker(spec,root,threads,frames[0])
    outputs=[]
    try:
        await worker.open()
        for frame in frames:
            r=await worker.infer(frame)
            outputs.append(tuple(Detection.model_validate(d) for d in r["detections"]))
    finally:
        await worker.close()
    match=[parity(a,b) for a,b in zip(reference,outputs)] if reference is not None else [True]*len(outputs)
    return outputs,dict(threads=threads,frames=len(outputs),matches=sum(match),
        parity=all(match) and len(outputs)==len(frames),reference=reference is None,
        nonempty_frames=sum(bool(x) for x in outputs),
        per_frame_matches=match)

def write_report(path,report):
    report=dict(report);report["result_sha256"]=fingerprint(report);write(path,report)

async def campaign(spec,root,holdouts,output):
    hw=cpu_budget();order=trial_order(hw["thread_budget"])
    frames=synthetic_frames()
    report=dict(scope="fr_perf_01a_memory_only_not_field",model_sha256=spec.sha256,hardware=hw,
        input_jpeg_sha256=[sha256(x).hexdigest() for x in frames],order=order,
        trials=[],parity=[],error=None,physical_actuation=False,candidate_promoted=False,
        operationally_validated=False,pilot_ready=False,human_acceptance="PENDING_HUMAN",
        operational_decision="abstain",phase_b="NOT_RUN",soak_24h="NOT_RUN")
    try:
        # Use SI10A's exact holdout identity checks and tolerances; no image persists.
        frozen=[encode(x) for case in HOLDOUTS for x in read_frames(case,holdouts/HOLDOUTS[case][0])]
        if len(frozen)!=64:raise ValueError("holdout sample count mismatch")
        report["parity_jpeg_sha256"]=[sha256(x).hexdigest() for x in frozen]
        ref=None
        async with asyncio.timeout(240):
            for n in order[0]:
                det,p=await parity_trial(frozen,n,spec,root,ref)
                if ref is None:ref=det
                report["parity"].append(p)
                write_report(output/f"parity-{n}.json",p)
                if not p["parity"] or not p["nonempty_frames"]:
                    raise ValueError("parity failure or vacuous parity")
        for i,n in enumerate([n for rotation in order for n in rotation],1):
            trial=await run_trial(frames,n,spec,root)
            trial["trial"]=i
            report["trials"].append(trial)
            write_report(output/f"trial-{i:02d}.json",trial)
            if not trial["technical_gate"]:raise ValueError("invalid trial evidence")
    except Exception as exc:
        report["error"]=type(exc).__name__+":"+str(exc)[:160]
    finally:
        report["complete"]=report["error"] is None and len(report["trials"])==sum(map(len,order))
        report["comparisons"]=[]
        if report["complete"]:
            baseline=[t["summary"] for t in report["trials"] if t["threads"]==1]
            for n in order[0]:
                selected=[t["summary"] for t in report["trials"] if t["threads"]==n]
                base=median([s["inference_ms"]["p95"] for s in baseline])
                cand=median([s["inference_ms"]["p95"] for s in selected])
                age=median([s["offer_to_analytics_ms"]["p95"] for s in selected])
                share=median([s["completion_share"] for s in selected])
                improvement=(base-cand)/base if base>0 else None
                report["comparisons"].append(dict(threads=n,median_inference_p95=cand,
                    median_age_p95=age,median_completion_share=share,relative_improvement=improvement,
                    all_capacity_gates=all(s["capacity_gate"] for s in selected),
                    exploratory_gate=n!=1 and improvement is not None and improvement>=.2
                    and age<=median([s["offer_to_analytics_ms"]["p95"] for s in baseline])
                    and share>=median([s["completion_share"] for s in baseline])))
        write_report(output/"campaign.json",report)
    return report["complete"]

def main():
    p=argparse.ArgumentParser()
    for name in ("model-spec","model-root","holdouts","output"):p.add_argument("--"+name,required=True)
    p.add_argument("--authorize-phase-a",action="store_true")
    a=p.parse_args()
    if not a.authorize_phase_a:p.error("explicit phase A authorization required")
    output=private_path(a.output)
    if not output.is_dir():raise ValueError("private output directory required")
    spec=load_json_model(a.model_spec,ModelSpec);root=Path(a.model_root)
    if (spec.sha256!=YOLOX_S_SHA256 or spec.purpose!="validation_only" or spec.architecture!="yolox"
        or spec.confidence!=.25 or spec.nms_iou!=.45 or sha256_file(spec.resolve(root))!=spec.sha256):
        raise ValueError("pinned validation model required")
    if not asyncio.run(campaign(spec,root,Path(a.holdouts),output)):raise SystemExit(1)

if __name__=="__main__":main()
