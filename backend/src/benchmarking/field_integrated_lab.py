"""One bounded synthetic loopback experiment; never field evidence."""
import argparse
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import resource
from time import monotonic,process_time
from src.analytics.contracts import SourceGeometry
from src.analytics.service import AnalyticsService
from src.archive.store import fingerprint
from src.benchmarking.pimcat_i2b_resilience import publisher,terminate,distribution
from src.benchmarking.si10b_shadow_load import process_sample
from src.tracking.service import TrackingService
from src.validation.io import load_json_model
from src.video.contracts import SourceSpec
from src.video.manager import VideoManager
from src.vision.contracts import ModelSpec
from src.vision.model_artifacts import YOLOX_S_SHA256
from src.vision.service import VisionService,InferenceWorker

KEY="LAB_FAULT"
COUNTERS=("capture","vision","tracking","analytics")
class MeasuredTracking(TrackingService):
    def __init__(self,vision):
        super().__init__(vision);self.events=[]
    def consume(self,batch):
        super().consume(batch)
        snap=self.analytics.latest(batch.source_id)
        if snap is not None and snap.session_id==batch.session_id and snap.frame_sequence==batch.frame_sequence:
            self.events.append({"session":str(batch.session_id),"sequence":batch.frame_sequence,"inference_ms":batch.inference_ms,
                "receive_to_analytics_ms":max(0.,(datetime.now(timezone.utc)-batch.received_at).total_seconds()*1000)})

def summarize(rows,events,elapsed,cleanup,error,failures,counts):
    gaps=[b["t"]-a["t"] for a,b in zip(rows,rows[1:])]
    span=rows[-1]["t"]-rows[0]["t"] if len(rows)>1 else 0
    delta={k:rows[-1][k]-rows[0][k] if rows else 0 for k in COUNTERS}
    monotone=all(b[k]>=a[k] for a,b in zip(rows,rows[1:]) for k in COUNTERS)
    off,on=events.get("off"),events.get("on")
    before=[r for r in rows if off is not None and r["t"]<off]
    lost=[r for r in rows if off is not None and on is not None and off<=r["t"]<on and not r["recent"]]
    baseline=[r for r in rows if on is not None and r["t"]<on]
    recovery=None
    if before and lost and baseline:
        for r in rows:
            if r["t"]>=on and r["recent"] and r["capture"]>baseline[-1]["capture"] and r["session"]!=before[-1]["session"] and r["analytics_session"]==r["session"] and r["analytics"]>baseline[-1]["analytics"]:
                recovery=r["t"]-on;break
    checks=dict(duration=elapsed>=100,coverage=len(rows)>=95,sampling_gap=bool(gaps) and 0<min(gaps) and max(gaps)<=3,
        fault_timing=off is not None and on is not None and 20<=off<=23 and 40<=on<=43,
        recovery=recovery is not None and 0<=recovery<=45,progress=monotone and all(v>0 for v in delta.values()),
        stage_conservation=counts["vision"]==counts["tracking"]==counts["analytics"] and counts["vision"]>0,
        no_stage_failures=not any(failures.values()),cleanup=cleanup,no_error=error is None)
    return dict(deltas=delta,sample_span_seconds=span,fps={k:v/span if span>0 and monotone else None for k,v in delta.items()},
        sampled_recent_share=sum(r["recent"] for r in rows)/len(rows) if rows else None,
        decode_receive_ms=distribution([r["decode_receive_ms"] for r in rows if r["decode_receive_ms"] is not None]),
        recovery_seconds=recovery,unknown_observed=bool(lost),checks=checks)

async def run(spec,model_root,root):
    if spec.sha256!=YOLOX_S_SHA256 or spec.purpose!="validation_only" or spec.architecture!="yolox":raise ValueError("pinned model required")
    source=SourceSpec(source_id=KEY,intersection_code="LAB_CR",kind="rtsp",locator="rtsp://127.0.0.1:18554/"+KEY,
        continuous=True,authorization_ref="synthetic-loopback-only",target_fps=5,reconnect_attempts=0)
    manager=VideoManager([source],root);worker=InferenceWorker(spec,model_root)
    vision=VisionService(manager,spec,model_root,worker_factory=lambda *_:worker);track=MeasuredTracking(vision)
    geom=SourceGeometry.model_validate(dict(source_id=KEY,intersection_code="LAB_CR",regions=[dict(region_id="lab",xyxy=[.1,.1,.9,.9])],lines=[dict(line_id="lab_line",start=[.1,.5],end=[.9,.5])]))
    analytics=AnalyticsService(track,{KEY:geom});vision.tracking=track;track.analytics=analytics
    rows=[];events={};latencies=[];resources=[];pub=None;start=None;elapsed=0.;error=None;cpu=process_time();event_start=0
    try:
        pub=publisher(KEY);await asyncio.sleep(2);manager.start_supervisor();vision.start()
        async with asyncio.timeout(60):
            while analytics.processed<2 or vision.state!="ready":
                if vision.state=="error" or pub.poll() is not None:raise RuntimeError("warmup_failed")
                await asyncio.sleep(.2)
        start=monotonic();next_sample=start;event_start=len(track.events)
        while monotonic()-start<100:
            t=monotonic()-start
            if t>=20 and "off" not in events:
                await terminate(pub);pub=None;events["off"]=monotonic()-start
            if t>=40 and "on" not in events:
                pub=publisher(KEY);events["on"]=monotonic()-start
            if pub is not None and pub.poll() is not None:raise RuntimeError("publisher_exited")
            if vision.state!="ready":raise RuntimeError("vision_failed")
            g=manager.gateway_status();assert g["physical_actuation"] is False and g["operational_decision"]=="abstain"
            x=g["sources"][0];s=manager.sessions[KEY];a=analytics.latest(KEY)
            rows.append(dict(t=monotonic()-start,recent=x["observation"]=="recent_frames",capture=x["process_observed_frames"],
                restarts=x["supervisor_restarts"],session=str(s.session_id),analytics_session=str(a.session_id) if a else None,
                vision=vision.processed,tracking=track.processed,analytics=analytics.processed,discarded=vision.discarded,decode_receive_ms=x["decode_to_receive_ms"]))
            sample=process_sample(worker)
            if sample is not None:resources.append(sample)
            next_sample+=1
            if next_sample<monotonic():next_sample=monotonic()+1
            await asyncio.sleep(max(0,next_sample-monotonic()))
        elapsed=monotonic()-start;latencies=track.events[event_start:]
    except Exception as exc:
        error=type(exc).__name__
        if start is not None:elapsed=monotonic()-start;latencies=track.events[event_start:]
    finally:
        await vision.shutdown();await manager.shutdown();await terminate(pub)
    cleanup=vision.task is None and worker.process is None and manager.supervisor_task is None and manager.status()["active"]==0 and (pub is None or pub.poll() is not None)
    counts=dict(vision=vision.processed,tracking=track.processed,analytics=analytics.processed)
    failures=dict(tracking=track.failed,analytics=analytics.failed)
    summary=summarize(rows,events,elapsed,cleanup,error,failures,counts)
    report=dict(scope="integrated_synthetic_loopback_not_field",model_sha256=spec.sha256,elapsed_seconds=elapsed,rows=rows,events=events,
        latency_events=latencies,worker_samples=resources,parent_cpu_seconds=process_time()-cpu,parent_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        worker_cpu_seconds=resources[-1]["cpu_seconds"]-resources[0]["cpu_seconds"] if len(resources)>1 else None,
        worker_peak_sampled_rss_kib=max((r["rss_kib"] for r in resources),default=None),inference_ms=distribution([x["inference_ms"] for x in latencies]),
        receive_to_analytics_ms=distribution([x["receive_to_analytics_ms"] for x in latencies]),stage_counts=counts,failures=failures,error_type=error,cleanup=cleanup,
        summary=summary,technical_gate_passed=all(summary["checks"].values()),source_latency_ms=None,field_accuracy=None,process_tree_rss=None,
        soak_24h="NOT_RUN",human_acceptance="PENDING_HUMAN",physical_actuation=False,candidate_promoted=False,operationally_validated=False,pilot_ready=False,operational_decision="abstain")
    report["result_sha256"]=fingerprint(report);return report

def verify(report):
    r=dict(report);sha=r.pop("result_sha256")
    assert sha==fingerprint(r) and r["scope"]=="integrated_synthetic_loopback_not_field" and r["model_sha256"]==YOLOX_S_SHA256
    assert r["summary"]==summarize(r["rows"],r["events"],r["elapsed_seconds"],r["cleanup"],r["error_type"],r["failures"],r["stage_counts"])
    assert r["technical_gate_passed"]==all(r["summary"]["checks"].values())
    assert r["inference_ms"]==distribution([x["inference_ms"] for x in r["latency_events"]])
    assert r["receive_to_analytics_ms"]==distribution([x["receive_to_analytics_ms"] for x in r["latency_events"]])
    assert r["operational_decision"]=="abstain" and r["human_acceptance"]=="PENDING_HUMAN" and r["soak_24h"]=="NOT_RUN"
    assert all(r[k] is False for k in ("physical_actuation","candidate_promoted","operationally_validated","pilot_ready"))
    return r["technical_gate_passed"]

def main():
    p=argparse.ArgumentParser();p.add_argument("--model-spec",required=True);p.add_argument("--model-root",required=True);p.add_argument("--output",required=True);p.add_argument("--authorize-bounded-lab",action="store_true");a=p.parse_args()
    if not a.authorize_bounded_lab:p.error("explicit bounded lab authorization required")
    assert __debug__
    path=Path(a.output);assert not path.exists()
    r=asyncio.run(run(load_json_model(a.model_spec,ModelSpec),Path(a.model_root),path.parent))
    with path.open("x") as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False)
    assert verify(r),"integrated lab technical gate failed"
if __name__=="__main__":main()
