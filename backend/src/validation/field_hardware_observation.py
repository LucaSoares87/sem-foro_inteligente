"""Bounded read-only local health sampling. Never controls capture or signals."""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import re
from time import monotonic,sleep
import urllib.request
from src.validation.field_readiness import require,ref,digest,number,write,result
from src.validation.field_jaad_range import opener

def counter(x):return x if type(x)is int and x>=0 else None
def metric(x):return float(x) if number(x) and x>=0 else None
def quantile(values):
    x=sorted(v for v in values if v is not None)
    return {"count":len(x),"p50":x[math.ceil(.5*len(x))-1] if x else None,"p95":x[math.ceil(.95*len(x))-1] if x else None,"max":x[-1] if x else None}

def snapshot(payload,source):
    g=payload["live_gateway"];require(g.get("physical_actuation") is False and g.get("operational_decision")=="abstain","unsafe scope")
    rows=[x for x in g["sources"] if x["source_id"]==source];require(len(rows)==1,"source unavailable")
    x=rows[0];v=payload["vision"];ys=[y for y in v["sources"] if y["source_id"]==source];require(len(ys)<=1,"ambiguous inference")
    y=ys[0] if ys else {};recent=x["observation"]=="recent_frames"
    return {"recent":recent,"frames":counter(x.get("process_observed_frames")),"restarts":counter(x.get("supervisor_restarts")),
        "session_overwrites":counter(x.get("session_buffer_overwrites")),"decode_receive_ms":metric(x.get("decode_to_receive_ms")) if recent else None,
        "latest_inference_ms":metric(y.get("inference_ms")),"inferred_at":y.get("inferred_at") if isinstance(y.get("inferred_at"),str) else None,
        "inference_frame":counter(y.get("frame_sequence")),"model_sha256":v.get("model_sha256") if digest(v.get("model_sha256")) else None,
        "global_processed":counter(v.get("processed")),"global_discarded":counter(v.get("discarded"))}

def resources(path):
    if path is None:return None
    try:
        d=dict(line.split() for line in (path/"cpu.stat").read_text().splitlines())
        cpu=int(d["usage_usec"]);mem=int((path/"memory.current").read_text())
        if cpu<0 or mem<0:return None
        return {"cpu_usage_usec":cpu,"memory_current_bytes":mem}
    except (OSError,ValueError,KeyError):return None

def summarize(rows,source,authorization,interval):
    require(len(rows)>=2 and all(number(x["t"]) for x in rows),"invalid timeline")
    times=[r["t"] for r in rows];require(all(b>a for a,b in zip(times,times[1:])),"nonmonotonic samples")
    s=[r["capture"] for r in rows if r["capture"] is not None];elapsed=times[-1]-times[0]
    def stable(key):
        vals=[x[key] for x in s]
        return len(s)==len(rows) and all(x is not None for x in vals) and all(b>=a for a,b in zip(vals,vals[1:]))
    complete=(len(s)==len(rows) and all(b-a<=2*interval+2 for a,b in zip(times,times[1:]))
              and len({x["model_sha256"] for x in s})==1 and s[0]["model_sha256"] is not None
              and stable("frames") and stable("restarts") and s[0]["restarts"]==s[-1]["restarts"])
    latest={}
    for x in s:
        if x["model_sha256"] and x["inferred_at"] and x["inference_frame"] is not None and x["latest_inference_ms"] is not None:
            latest[(x["model_sha256"],x["inferred_at"],x["inference_frame"])]=x["latest_inference_ms"]
    rs=[x["resource"] for x in rows]
    cpu=None
    if all(x is not None for x in rs) and all(b["cpu_usage_usec"]>=a["cpu_usage_usec"] for a,b in zip(rs,rs[1:])):
        cpu=(rs[-1]["cpu_usage_usec"]-rs[0]["cpu_usage_usec"])/1e6/elapsed
    return result("private_sampled_hardware_observation_not_gate",source_id=source,authorization_ref_sha256=__import__("hashlib").sha256(authorization.encode()).hexdigest(),
        samples=rows,observed_samples=len(s),expected_samples=len(rows),recent_samples=sum(x["recent"] for x in s),
        elapsed_seconds=elapsed,sustained_capture_fps=(s[-1]["frames"]-s[0]["frames"])/elapsed if complete else None,
        capture_counter_continuity=bool(complete),decode_receive_ms=quantile([x["decode_receive_ms"] for x in s]),
        distinct_latest_inference_ms=quantile(list(latest.values())),http_latency_ms=quantile([x["http_ms"] for x in rows]),
        cgroup_average_cpu_cores=cpu,cgroup_memory_current_bytes=quantile([x["memory_current_bytes"] for x in rs if x is not None]),
        source_latency_ms=None,end_to_end_latency_ms=None,source_dropped_frames=None,process_tree_rss=None,hardware_gate="NOT_REGISTERED")

def collect(source,authorization,samples,interval,port,cgroup):
    require(ref(authorization) and re.fullmatch(r"[A-Za-z0-9_-]{2,80}",source) is not None,"authorized source required")
    require(type(samples)is int and 2<=samples<=600 and 1<=interval<=10 and port in (5173,8000),"invalid bounds")
    client=opener();rows=[];start=monotonic();url=f"http://127.0.0.1:{port}/api/v1/health"
    for i in range(samples):
        begin=monotonic();capture=None;error=None
        try:
            with client.open(url,timeout=2) as r:
                require(r.status==200 and r.geturl()==url,"invalid health response");raw=r.read(2_000_001);require(len(raw)<=2_000_000,"health response limit")
                capture=snapshot(json.loads(raw),source)
        except (OSError,ValueError,KeyError,TypeError) as exc:error=type(exc).__name__
        rows.append({"t":monotonic()-start,"utc":datetime.now(timezone.utc).isoformat(),"http_ms":(monotonic()-begin)*1000,
                     "capture":capture,"resource":resources(cgroup),"error_type":error})
        if i+1<samples:sleep(max(0,interval-(monotonic()-begin)))
    return summarize(rows,source,authorization,interval)
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",required=True);p.add_argument("--authorization-ref",required=True);p.add_argument("--samples",type=int,default=120);p.add_argument("--interval",type=float,default=1);p.add_argument("--port",type=int,default=5173);p.add_argument("--cgroup");p.add_argument("--output",required=True);a=p.parse_args()
    cg=Path(a.cgroup).resolve() if a.cgroup else None
    require(cg is None or cg.is_relative_to("/sys/fs/cgroup"),"cgroup v2 path required")
    write(a.output,collect(a.source,a.authorization_ref,a.samples,a.interval,a.port,cg))
if __name__=="__main__":main()
