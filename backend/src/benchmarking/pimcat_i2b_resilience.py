"""Synthetic loopback-only resilience harness; no production integration."""
import argparse
import asyncio
import json
import math
import resource
import subprocess
from pathlib import Path
from time import monotonic, process_time
from src.archive.store import fingerprint
from src.video.contracts import SourceSpec
from src.video.manager import VideoManager

PROFILES={"ci":(180,((30,50),(100,120))),"dedicated":(86400,((3600,3620),(43200,43220),(79200,79220)))}
KEYS=("LAB_CONTROL","LAB_FAULT")

def distribution(values):
    if not values:return None
    x=sorted(values)
    return {"count":len(x),"p50":x[math.ceil(.5*len(x))-1],"p95":x[math.ceil(.95*len(x))-1],"max":x[-1]}

def summarize(rows,events,profile,elapsed,cleanup):
    duration,windows=PROFILES[profile]
    result={}
    for key in KEYS:
        s=[r["sources"][key] for r in rows]
        outside=[v for r,v in zip(rows,s) if not any(a<=r["t"]<b for a,b in windows)]
        frames=[v["frames"] for v in s]
        result[key]={"samples":len(s),"recent_share":sum(v["recent"] for v in s)/len(s) if s else 0,
                     "outside_fault_recent_share":sum(v["recent"] for v in outside)/len(outside) if outside else None,
                     "frames_delta":frames[-1]-frames[0] if frames else 0,
                     "monotonic_frames":all(b>=a for a,b in zip(frames,frames[1:])),
                     "fps":distribution([v["fps"] for v in s if v["fps"] is not None]),
                     "decode_receive_ms":distribution([v["latency"] for v in s if v["latency"] is not None]),
                     "restarts":s[-1]["restarts"] if s else 0}
    gaps=[b["t"]-a["t"] for a,b in zip(rows,rows[1:])]
    checks={"duration":elapsed>=duration,"sample_coverage":len(rows)>=math.ceil(.95*duration),
            "sampling_gap":bool(gaps) and max(gaps)<=3,
            "control_recent":result["LAB_CONTROL"]["recent_share"]>=.95,
            "capture_observed":all(v["frames_delta"]>0 and v["fps"] and v["decode_receive_ms"] and v["monotonic_frames"] for v in result.values()),
            "fault_recovery":len(events)==len(windows) and all(e["unknown_seen"] and e["recovery_seconds"] is not None and 0<=e["recovery_seconds"]<=45 for e in events),
            "cleanup":cleanup}
    return result,checks

def publisher(key):
    return subprocess.Popen(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-re","-f","lavfi","-i","testsrc2=size=320x240:rate=10",
        "-c:v","libx264","-threads","1","-preset","ultrafast","-tune","zerolatency","-g","10","-f","rtsp","-rtsp_transport","tcp",
        "rtsp://127.0.0.1:18554/"+key],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

async def terminate(p):
    if p is not None:
        if p.poll() is None:
            p.terminate()
            try:await asyncio.to_thread(p.wait,5)
            except subprocess.TimeoutExpired:
                p.kill();await asyncio.to_thread(p.wait,5)

async def run(profile,root):
    duration,windows=PROFILES[profile]
    specs=[SourceSpec(source_id=k,intersection_code="LAB_CR",kind="rtsp",locator="rtsp://127.0.0.1:18554/"+k,
         continuous=True,authorization_ref="local-synthetic-i2b-only",target_fps=5,reconnect_attempts=0) for k in KEYS]
    manager=VideoManager(specs,root)
    publishers={k:None for k in KEYS};rows=[];events=[];cleanup=False
    start=None;elapsed=0;cpu=process_time();failure=None
    try:
        for k in KEYS:publishers[k]=publisher(k)
        await asyncio.sleep(2)
        manager.start_supervisor()
        deadline=monotonic()+45
        while not all(s.state=="running" and s.frames>=10 for s in manager.sessions.values()):
            if monotonic()>=deadline or any(p.poll() is not None for p in publishers.values()):raise RuntimeError("warmup_failed")
            await asyncio.sleep(.25)
        start=monotonic();next_sample=start
        while monotonic()-start<duration:
            t=monotonic()-start
            for index,(off,on) in enumerate(windows):
                if t>=off and len(events)==index:
                    await terminate(publishers["LAB_FAULT"]);publishers["LAB_FAULT"]=None
                    events.append({"off":monotonic()-start,"on":None,"unknown_seen":False,"recovery_seconds":None,"baseline_frames":manager.gateway_status()["sources"][1]["process_observed_frames"]})
                if index<len(events) and t>=on and events[index]["on"] is None:
                    publishers["LAB_FAULT"]=publisher("LAB_FAULT")
                    events[index]["on"]=monotonic()-start
            status=manager.gateway_status()
            assert status["physical_actuation"] is False and status["operational_decision"]=="abstain"
            current={}
            for v in status["sources"]:
                k=v["source_id"];recent=v["observation"]=="recent_frames"
                current[k]={"recent":recent,"frames":v["process_observed_frames"],"fps":v["measured_fps"],
                            "latency":v["decode_to_receive_ms"],"restarts":v["supervisor_restarts"],"age":v["last_frame_age_seconds"]}
            t=monotonic()-start
            if events:
                ev=events[-1];f=current["LAB_FAULT"]
                if ev["on"] is None and not f["recent"]:ev["unknown_seen"]=True
                if ev["on"] is not None and ev["recovery_seconds"] is None and f["recent"] and f["frames"]>ev["baseline_frames"]:
                    ev["recovery_seconds"]=t-ev["on"]
            rows.append({"t":t,"sources":current})
            if any(p is not None and p.poll() is not None for p in publishers.values()):raise RuntimeError("publisher_exited")
            next_sample+=1
            if next_sample<monotonic():next_sample=monotonic()+1
            await asyncio.sleep(max(0,next_sample-monotonic()))
        elapsed=monotonic()-start
    except Exception as exc:
        failure=type(exc).__name__
        if start is not None:elapsed=monotonic()-start
    finally:
        await manager.shutdown()
        for p in publishers.values():await terminate(p)
        cleanup=manager.supervisor_task is None and manager.status()["active"]==0 and all(p is None or p.poll() is not None for p in publishers.values())
    summary,checks=summarize(rows,events,profile,elapsed,cleanup)
    report={"scope":"synthetic_loopback_rtsp_not_field","profile":profile,"elapsed_seconds":elapsed,"samples":rows,
            "events":events,"summary":summary,"checks":checks,"error_type":failure,
            "python_peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"python_cpu_seconds":process_time()-cpu,
            "technical_gate_passed":failure is None and all(checks.values()),
            "soak_24h":"EXECUTED_SYNTHETIC" if profile=="dedicated" and elapsed>=86400 and failure is None else "NOT_RUN",
            "rtsps":"NOT_RUN","municipal_vms":"BLOCKED","c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION",
            "inference_measured":False,"physical_actuation":False,"operationally_validated":False,
            "commercial_demo_authorized":False,"candidate_promoted":False,"operational_decision":"abstain"}
    report["result_sha256"]=fingerprint(report)
    return report

def verify(report):
    r=dict(report);h=r.pop("result_sha256");assert fingerprint(r)==h
    assert r["scope"]=="synthetic_loopback_rtsp_not_field"
    summary,checks=summarize(r["samples"],r["events"],r["profile"],r["elapsed_seconds"],r["checks"]["cleanup"])
    assert r["summary"]==summary and r["checks"]==checks
    assert r["technical_gate_passed"]==(r["error_type"] is None and all(checks.values()))
    assert r["operational_decision"]=="abstain" and all(r[k] is False for k in ("physical_actuation","operationally_validated","commercial_demo_authorized","candidate_promoted","inference_measured"))
    assert r["c3_independent_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"
    assert r["soak_24h"]==("EXECUTED_SYNTHETIC" if r["profile"]=="dedicated" and r["elapsed_seconds"]>=86400 and r["error_type"] is None else "NOT_RUN")
    return r["technical_gate_passed"]

def main():
    p=argparse.ArgumentParser();p.add_argument("--profile",choices=PROFILES,default="ci");p.add_argument("--output",required=True)
    p.add_argument("--authorize-dedicated-host",action="store_true");a=p.parse_args()
    if a.profile=="dedicated" and not a.authorize_dedicated_host:p.error("dedicated host and cost authorization required")
    import os
    if a.profile=="dedicated" and os.environ.get("GITHUB_ACTIONS"):p.error("dedicated profile forbidden in hosted CI")
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    report=asyncio.run(run(a.profile,path.parent))
    with path.open("x") as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({"summary":report["summary"],"checks":report["checks"]},sort_keys=True))
    assert verify(report),"resilience technical gate failed"

if __name__=="__main__":main()
