#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

def canonical(value):
    return json.dumps(value,separators=(",",":"),sort_keys=True,ensure_ascii=False).encode()

def percentile(values,p):
    if not values:
        return 0.0
    values=sorted(values)
    return values[min(len(values)-1,max(0,int(round((len(values)-1)*p))))]

def memory_mb():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1])/1024,1)
    except OSError:
        pass
    try:
        pages=os.sysconf("SC_PHYS_PAGES")
        size=os.sysconf("SC_PAGE_SIZE")
        return round(pages*size/1024/1024,1)
    except (ValueError,OSError,AttributeError):
        return None

def fetch_health(url,timeout):
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(url,timeout=timeout) as response:
            raw=response.read(2_000_000)
            status=response.status
    except urllib.error.HTTPError as exc:
        raw=exc.read(2_000_000)
        status=exc.code
    latency=(time.perf_counter()-start)*1000
    try:
        payload=json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        payload=None
    return status,payload,latency

def write_report(path,payload):
    body=dict(payload)
    body["artifact_sha256"]=hashlib.sha256(canonical(body)).hexdigest()
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+".tmp")
    temp.write_text(json.dumps(body,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    os.chmod(temp,0o600)
    temp.replace(target)
    return body

def main():
    parser=argparse.ArgumentParser(description="Collect SI-08B target-hardware evidence without sending control commands.")
    parser.add_argument("--base-url",default="http://127.0.0.1:5173")
    parser.add_argument("--samples",type=int,default=10)
    parser.add_argument("--interval",type=float,default=.5)
    parser.add_argument("--timeout",type=float,default=5)
    parser.add_argument("--output",required=True)
    parser.add_argument("--require-workload",action="store_true")
    args=parser.parse_args()
    if not (2<=args.samples<=600 and .05<=args.interval<=60 and .5<=args.timeout<=30):
        raise SystemExit("invalid probe limits")
    url=args.base_url.rstrip("/")+"/api/v1/health"
    snapshots=[]
    latencies=[]
    errors=0
    started=time.monotonic()
    for index in range(args.samples):
        status,payload,latency=fetch_health(url,args.timeout)
        latencies.append(latency)
        if status!=200 or not isinstance(payload,dict):
            errors+=1
        else:
            snapshots.append(payload)
        if index+1<args.samples:
            time.sleep(args.interval)
    elapsed=max(.001,time.monotonic()-started)
    first=snapshots[0] if snapshots else {}
    last=snapshots[-1] if snapshots else {}
    def counter(section,key="processed"):
        a=first.get(section,{}).get(key,0)
        b=last.get(section,{}).get(key,0)
        return max(0,b-a) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else 0
    video_delta={}
    first_sources={x.get("source_id"):x for x in first.get("video",{}).get("sources",[]) if x.get("source_id")}
    for item in last.get("video",{}).get("sources",[]):
        source=item.get("source_id")
        if not source:
            continue
        before=first_sources.get(source,{})
        current=item.get("frames_received",0)
        previous=before.get("frames_received",0)
        video_delta[source]=max(0,current-previous) if isinstance(current,int) and isinstance(previous,int) else 0
    validation=last.get("validation",{})
    runtime=validation.get("runtime_observation",{})
    workload_ok=bool(runtime.get("authorized_candidate_model_loaded") and runtime.get("physical_sources_running",0)>0)
    payload={
        "schema_version":1,
        "captured_at":datetime.now(timezone.utc).isoformat(),
        "environment":{
            "platform":platform.system(),
            "release":platform.release(),
            "machine":platform.machine(),
            "python":platform.python_version(),
            "cpu_count":os.cpu_count(),
            "memory_total_mb":memory_mb(),
        },
        "probe":{
            "url":url,"samples_requested":args.samples,"samples_ready":len(snapshots),
            "errors":errors,"elapsed_seconds":round(elapsed,3),
            "latency_mean_ms":round(statistics.fmean(latencies),2) if latencies else 0,
            "latency_p95_ms":round(percentile(latencies,.95),2),
            "latency_max_ms":round(max(latencies),2) if latencies else 0,
        },
        "workload_observation":{
            "authorized_candidate_model_loaded":bool(runtime.get("authorized_candidate_model_loaded")),
            "physical_sources_configured":runtime.get("physical_sources_configured",0),
            "physical_sources_running":runtime.get("physical_sources_running",0),
            "vision_processed_delta":counter("vision"),
            "tracking_processed_delta":counter("tracking"),
            "analytics_processed_delta":counter("analytics"),
            "video_frames_delta":video_delta,
        },
        "evidence_state":"measured" if errors==0 and snapshots else "failed",
        "pilot_gate_satisfied":False,
        "physical_actuation":False,
        "note":"Measurement artifact only. Pilot gate requires approved thresholds and external evidence registration."
    }
    report=write_report(args.output,payload)
    print(json.dumps({"output":args.output,"artifact_sha256":report["artifact_sha256"],
                      "errors":errors,"workload_observed":workload_ok},sort_keys=True))
    if errors or not snapshots:
        return 2
    if args.require_workload and not workload_ok:
        return 5
    return 0

if __name__=="__main__":
    raise SystemExit(main())
