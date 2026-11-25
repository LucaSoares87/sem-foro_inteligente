"""Research-only wall-clock load replay; no change to runtime defaults."""
import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import cv2

from src.analytics.contracts import SourceGeometry
from src.analytics.service import AnalyticsService
from src.archive.store import fingerprint
from src.benchmarking.si09f_validation import HOLDOUTS, write_new
from src.benchmarking.si10_cpu_profile import PIXELS, cpu_budget, p95
from src.optimization.service import OptimizationService
from src.queueing.service import QueueService
from src.tracking.service import TrackingService
from src.validation.io import load_json_model, sha256_file
from src.video.contracts import MAX_JPEG, SourceSpec, VideoFrame
from src.video.manager import child_environment
from src.vision.contracts import ModelSpec
from src.vision.model_artifacts import YOLOX_S_SHA256
from src.vision.service import InferenceWorker, VisionService

DURATION = 12
RATES = (5, 2)
CASES = ("morning_0708", "morning_1108")


def read_load_inputs(case, source):
    """Verify the whole frozen span; retain only required, pre-encoded JPEGs."""
    name, digest = HOLDOUTS[case]
    source = Path(source)
    if source.name != name or sha256_file(source) != digest:
        raise ValueError("official source identity mismatch")
    cap = cv2.VideoCapture(str(source))
    pixels = hashlib.sha256()
    result = {rate: [] for rate in RATES}
    origin = previous = None
    try:
        if not cap.isOpened():
            raise ValueError("source not decodable")
        for i in range(961):
            ok, frame = cap.read()
            if not ok or frame is None or frame.shape != (720,1280,3):
                raise ValueError("source decode or resolution mismatch")
            if i == 0:
                continue
            stamp = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            if not math.isfinite(stamp) or stamp < 0:
                raise ValueError("invalid source timestamp")
            if origin is None:
                origin = stamp
            elif abs(stamp-previous-1/30) > .002 or abs(stamp-origin-(i-1)/30) > .002:
                raise ValueError("frozen span cadence mismatch")
            previous = stamp
            pixels.update(frame.tobytes())
            rates = [r for r in RATES if i-1 < DURATION*30 and (i-1)%(30//r)==0]
            if rates:
                ok, jpeg = cv2.imencode(".jpg",frame,[int(cv2.IMWRITE_JPEG_QUALITY),90])
                if not ok or not 0 < len(jpeg) <= MAX_JPEG:
                    raise ValueError("invalid JPEG")
                payload = jpeg.tobytes()
                for r in rates:
                    result[r].append(payload)
    finally:
        cap.release()
    if pixels.hexdigest() != PIXELS[case] or any(len(v)!=DURATION*r for r,v in result.items()):
        raise ValueError("frozen pixels or sampling schedule mismatch")
    return result


def child_main(threads):
    """Use the production worker protocol and detector; override only the child thread count."""
    if threads not in (1,2,4) or threads > cpu_budget()["thread_budget"]:
        raise ValueError("invalid research CPU budget")
    from src.vision import worker, yolo
    original = yolo.YoloDetector
    class ResearchDetector(original):
        def __init__(self,path,spec):
            super().__init__(path,spec)
            cv2.setNumThreads(threads)
            if cv2.getNumThreads() != threads:
                raise ValueError("thread setting not applied")
    yolo.YoloDetector = ResearchDetector
    return worker.main()


class ResearchWorker(InferenceWorker):
    def __init__(self,spec,root,threads,warmup):
        super().__init__(spec,root)
        self.threads, self.warmup = threads,warmup

    async def open(self):
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,"-m","src.benchmarking.si10b_shadow_load","--worker",
            "--threads",str(self.threads),stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            env=child_environment(),limit=65536)
        async with asyncio.timeout(30):
            payload={"spec":self.spec.model_dump(mode="json"),"root":str(self.root)}
            self.process.stdin.write(json.dumps(payload).encode()+b"\n")
            await self.process.stdin.drain()
            if (await self._reply()).get("state")!="ready":
                raise ValueError("research worker load failed")
        await self.infer(self.warmup)


class LatestReplay:
    """Memory-only replay adapter: one latest frame per source, no camera or RTSP."""
    def __init__(self,frames,rate):
        self.slots={}
        self.offered=Counter()
        self.overwritten=Counter()
        self.taken=Counter()
        self.sessions={}
        for key in frames:
            source=SourceSpec(source_id=key,intersection_code="BELLEVUE_116TH_NE12TH",
                kind="file",locator=HOLDOUTS[key][0],target_fps=rate,
                data_origin="external_real_replay",commercial_demo_authorized=False)
            self.sessions[key]=SimpleNamespace(spec=source,session_id=uuid4(),state="running")

    def publish(self,key,jpeg):
        session=self.sessions[key]
        self.offered[key]+=1
        if key in self.slots:
            self.overwritten[key]+=1
        self.slots[key]=VideoFrame(source_id=key,intersection_code=session.spec.intersection_code,
            session_id=session.session_id,sequence=self.offered[key],width=1280,height=720,
            received_at=datetime.now(timezone.utc),decode_to_receive_ms=0.,jpeg=jpeg)

    def take_latest(self,key):
        frame=self.slots.pop(key,None)
        if frame is not None:
            self.taken[key]+=1
        return frame


def process_sample(worker):
    """Linux process CPU/RSS snapshot; unavailable values remain unknown."""
    process=getattr(worker,"process",None)
    pid=getattr(process,"pid",None)
    if pid is None:
        return None
    try:
        stat=Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()
        cpu=(int(stat[11])+int(stat[12]))/os.sysconf("SC_CLK_TCK")
        status=Path(f"/proc/{pid}/status").read_text().splitlines()
        rss=next(int(x.split()[1]) for x in status if x.startswith("VmRSS:"))
        return {"cpu_seconds":cpu,"rss_kib":rss}
    except (OSError,ValueError,IndexError,StopIteration):
        return None


class MeasuredTracking(TrackingService):
    def __init__(self,vision,rate):
        super().__init__(vision)
        self.rate=rate
        self.started=None
        self.completed=defaultdict(list)

    def consume(self,batch):
        super().consume(batch)
        result=self.queue_intelligence.optimizer.latest(batch.source_id)
        tracked=self.results.get(batch.source_id)
        queued=self.queue_intelligence.results.get(batch.source_id)
        if (tracked is None or queued is None or result is None
                or tracked.frame_sequence!=batch.frame_sequence or queued.frame_sequence!=batch.frame_sequence
                or result.frame_sequence!=batch.frame_sequence
                or result.preferred_in_simulation!="abstain" or result.dynamic_x_safe_vehicles is not None
                or result.physical_actuation):
            raise ValueError("research pipeline error or non-abstention")
        now=monotonic()
        due=self.started+(batch.frame_sequence-1)/self.rate
        self.completed[batch.source_id].append((now,1000*(now-due),batch.inference_ms))


async def run_load(frames,rate,threads,spec,root,geometry,*,worker_factory=None):
    if rate not in RATES or threads not in (1,2,4) or not 1<=len(frames)<=2:
        raise ValueError("invalid research workload")
    if any(k not in CASES for k in frames) or len({len(v) for v in frames.values()})!=1:
        raise ValueError("invalid source schedule")
    n=len(next(iter(frames.values())))
    if not 1<=n<=DURATION*rate or any(a.visibility_calibrated for a in geometry.approaches):
        raise ValueError("invalid uncalibrated replay")
    duration=n/rate
    video=LatestReplay(frames,rate)
    warmup=next(iter(frames.values()))[0]
    worker=(worker_factory or ResearchWorker)(spec,root,threads,warmup)
    vision=VisionService(video,spec,root,worker_factory=lambda _s,_r:worker)
    tracking=MeasuredTracking(vision,rate)
    geometries={key:SourceGeometry.model_validate({**geometry.model_dump(),"source_id":key})
                for key in frames}
    analytics=AnalyticsService(tracking,geometries)
    queue=QueueService(tracking,analytics,geometries)
    optimizer=OptimizationService()
    vision.tracking=tracking
    tracking.analytics=analytics
    tracking.queue_intelligence=queue
    queue.optimizer=optimizer
    producer=None
    samples=[]
    publication_lags=[]
    try:
        vision.start()
        async with asyncio.timeout(45):
            while vision.state!="ready":
                if vision.state=="error":
                    raise ValueError("vision failed to initialize")
                await asyncio.sleep(.01)
        start=monotonic()
        tracking.started=start
        initial=process_sample(worker)
        if initial is not None:
            samples.append(initial)
        async def produce():
            for i in range(n):
                due=start+i/rate
                await asyncio.sleep(max(0,due-monotonic()))
                for key,values in frames.items():
                    publication_lags.append(max(0.,1000*(monotonic()-due)))
                    video.publish(key,values[i])
        producer=asyncio.create_task(produce())
        async with asyncio.timeout(duration+15):
            while True:
                if vision.state!="ready" or tracking.failed or analytics.failed or queue.failed or optimizer.failed:
                    raise ValueError("research pipeline failed")
                sample=process_sample(worker)
                if sample is not None:
                    samples.append(sample)
                done=sum(len(v) for v in tracking.completed.values())
                if producer.done() and monotonic()>=start+duration and not video.slots and done==sum(video.taken.values()):
                    await producer
                    break
                await asyncio.sleep(.02)
        elapsed=monotonic()-start
        if (vision.processed!=tracking.processed or tracking.processed!=analytics.processed
                or analytics.processed!=queue.processed or vision.processed!=sum(video.taken.values())):
            raise ValueError("pipeline count mismatch")
        sources=[]
        for key in frames:
            events=tracking.completed[key]
            if video.offered[key]!=n or video.taken[key]!=len(events) or video.overwritten[key]+len(events)!=n:
                raise ValueError("latest-buffer accounting mismatch")
            ages=[e[1] for e in events]
            within=sum(e[0]<=start+duration for e in events)
            sources.append({"case":key,"offered":n,"processed":len(events),
                "overwritten":video.overwritten[key],"completed_within_window":within,
                "effective_fps":within/duration,"age_p95_ms":p95(ages) if ages else None,
                "inference_mean_ms":fmean(e[2] for e in events) if events else None,
                "meets_load_gate":within/n>=.95 and bool(ages) and p95(ages)<=1000/rate})
        ratios=[s["completed_within_window"]/n for s in sources]
        return {"threads":threads,"offered_fps_per_source":rate,"source_count":len(frames),
            "duration_seconds":duration,"elapsed_with_drain_seconds":elapsed,
            "sources":sources,"fairness_min_max_completion_ratio":min(ratios)/max(ratios) if max(ratios) else None,
            "publication_lag_p95_ms":p95(publication_lags),
            "worker_cpu_seconds":max(0.,samples[-1]["cpu_seconds"]-samples[0]["cpu_seconds"]) if len(samples)>1 else None,
            "worker_peak_sampled_rss_kib":max(s["rss_kib"] for s in samples) if samples else None,
            "meets_all_load_gates":all(s["meets_load_gate"] for s in sources),
            "max_pending_per_source":1,"optimization_state":"abstain","physical_actuation":False}
    finally:
        if producer is not None:
            if not producer.done():
                producer.cancel()
            await asyncio.gather(producer,return_exceptions=True)
        await vision.shutdown()


async def main_async(args):
    spec=load_json_model(args.model_spec,ModelSpec)
    geometry=load_json_model(args.geometry,SourceGeometry)
    if spec.sha256!=YOLOX_S_SHA256 or spec.architecture!="yolox" or spec.purpose!="validation_only":
        raise ValueError("pinned validation model required")
    inputs={key:read_load_inputs(key,Path(args.source_root)/HOLDOUTS[key][0]) for key in CASES}
    hw=cpu_budget()
    threads=[t for t in (1,2,4) if t<=hw["thread_budget"]]
    runs=[]
    for t in threads:
        for keys in ((CASES[0],),CASES):
            runs.append(await run_load({k:inputs[k][5] for k in keys},5,t,spec,args.model_root,geometry))
    # Lower offered rate is a capacity diagnostic, not a recommended perception rate.
    runs.append(await run_load({k:inputs[k][2] for k in CASES},2,max(threads),spec,args.model_root,geometry))
    result={"schema_version":1,"scope":"paced_offline_service_load_not_field",
        "source_hashes":{k:HOLDOUTS[k][1] for k in CASES},"decoded_pixel_hashes":PIXELS,
        "model_sha256":spec.sha256,"hardware":hw,"runs":runs,
        "candidate_promoted":False,"adaptive_fps_enabled":False,"engineering_recommended_min_fps":None,
        "independent_accuracy_validated":False,"commercial_demo_authorized":False,
        "operationally_validated":False,"physical_actuation":False}
    result["result_sha256"]=fingerprint(result)
    write_new(args.output,result)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--worker",action="store_true")
    p.add_argument("--threads",type=int)
    for arg in ("source-root","model-spec","model-root","geometry","output"):
        p.add_argument("--"+arg)
    args=p.parse_args()
    if args.worker:
        return child_main(args.threads)
    if not all(getattr(args,k) for k in ("source_root","model_spec","model_root","geometry","output")):
        p.error("research replay requires source root, model spec/root, geometry and output")
    asyncio.run(main_async(args))
    return 0


if __name__=="__main__":
    sys.exit(main())
