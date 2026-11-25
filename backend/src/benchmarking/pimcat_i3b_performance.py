"""Offline synthetic sample-quality history; not field telemetry."""
import argparse
from datetime import datetime,timedelta,timezone
import json
import math
import re
from pathlib import Path
from src.archive.store import fingerprint

MAX_MINUTES=1440
MAX_SOURCES=32
MAX_BYTES=64*1024*1024
SHA=re.compile(r"[0-9a-f]{64}")
SOURCE=re.compile(r"[A-Za-z0-9_-]{1,64}")

def require(ok,message):
    if not ok:raise ValueError(message)

def minute(value):
    require(isinstance(value,str),"invalid timestamp")
    dt=datetime.fromisoformat(value)
    require(dt.tzinfo is not None and dt.utcoffset()==timedelta(0)
            and dt.second==dt.microsecond==0 and value==dt.isoformat(),"canonical UTC minute required")
    return dt

def valid_number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def validate(record):
    d=dict(record);h=d.pop("minute_sha256",None)
    require(h==fingerprint(d),"minute digest mismatch")
    require(set(d)=={"schema_version","origin","source_id","config_sha256","minute","samples"},"invalid minute schema")
    require(d["schema_version"]==1 and d["origin"]=="synthetic_fixture","only synthetic evidence")
    require(isinstance(d["source_id"],str) and SOURCE.fullmatch(d["source_id"]),"invalid source")
    require(isinstance(d["config_sha256"],str) and SHA.fullmatch(d["config_sha256"]),"invalid configuration")
    dt=minute(d["minute"])
    require(isinstance(d["samples"],list) and len(d["samples"])<=60,"sample limit")
    slots=set()
    for s in d["samples"]:
        require(set(s)=={"slot","recent","fps","decode_receive_ms"},"invalid sample schema")
        require(type(s["slot"]) is int and 0<=s["slot"]<60 and s["slot"] not in slots,"invalid/duplicate slot")
        slots.add(s["slot"])
        require(type(s["recent"]) is bool,"invalid observation")
        for k in ("fps","decode_receive_ms"):
            require(s[k] is None or (s["recent"] and valid_number(s[k])),"invalid metric")
    return dt

def distribution(values):
    v=sorted(values)
    return {"count":len(v),"p50":v[math.ceil(.5*len(v))-1] if v else None,
            "p95":v[math.ceil(.95*len(v))-1] if v else None,"max":v[-1] if v else None}

def stats(records):
    samples=[s for r in records for s in r["samples"]]
    expected=60*len(records);observed=len(samples);recent=sum(s["recent"] for s in samples)
    missing=expected-observed
    return {"expected_slots":expected,"observed_slots":observed,"recent_slots":recent,
            "unknown_slots":observed-recent,"unobserved_slots":missing,
            "coverage":observed/expected if expected else None,
            "recent_share_observed":recent/observed if observed else None,
            "recent_fraction_lower":recent/expected if expected else None,
            "recent_fraction_upper":(recent+missing)/expected if expected else None,
            "fps":distribution([s["fps"] for s in samples if s["fps"] is not None]),
            "decode_receive_ms":distribution([s["decode_receive_ms"] for s in samples if s["decode_receive_ms"] is not None])}

def build(records,start,end,sources):
    a,b=minute(start),minute(end)
    n=(b-a).total_seconds()/60
    require(1<=n<=MAX_MINUTES and n.is_integer(),"interval limit")
    require(isinstance(sources,list) and 1<=len(sources)<=MAX_SOURCES and
            all(isinstance(s,str) and SOURCE.fullmatch(s) for s in sources)
            and len(set(sources))==len(sources),"invalid sources")
    require(isinstance(records,list) and len(records)<=int(n)*len(sources),"record limit")
    index={};groups={}
    for r in records:
        dt=validate(r);source=r["source_id"];key=(source,dt)
        require(source in sources and a<=dt<b and key not in index,"scope or duplicate minute")
        index[key]=r;groups.setdefault((source,r["config_sha256"]),[]).append(r)
    rows=[];missing=[]
    for source in sorted(sources):
        for k in range(int(n)):
            dt=a+timedelta(minutes=k);r=index.get((source,dt))
            if r is None:
                missing.append({"source_id":source,"minute":dt.isoformat()})
            else:
                rows.append({"source_id":source,"minute":dt.isoformat(),"config_sha256":r["config_sha256"],
                             "minute_sha256":r["minute_sha256"],**stats([r])})
    aggregates=[{"source_id":key[0],"config_sha256":key[1],"received_minutes":len(rs),**stats(rs)}
                for key,rs in sorted(groups.items())]
    out={"schema_version":1,"scope":"synthetic_performance_history_not_field","start":start,"end":end,
         "sources":sorted(sources),"minutes":rows,"missing_minutes":missing,"aggregates":aggregates,
         "expected_interval_source_minutes":int(n)*len(sources),"received_source_minutes":len(rows),
         "camera_uptime_physical":None,"source_latency_ms":None,"inference_latency_ms":None,"physical_speed":None,
         "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","soak_24h":"NOT_RUN",
         "field_speed_calibration":"NOT_RUN","physical_actuation":False,"operationally_validated":False,
         "commercial_demo_authorized":False,"candidate_promoted":False,"operational_decision":"abstain"}
    out["result_sha256"]=fingerprint(out)
    return out

def write_exclusive(path,report):
    with Path(path).open("x",encoding="utf-8") as f:json.dump(report,f,sort_keys=True,indent=2,allow_nan=False)

def fixture():
    start="2026-01-01T00:00:00+00:00";end="2026-01-01T00:03:00+00:00"
    records=[]
    for source,k,count,recent in [("LAB_A",0,60,True),("LAB_A",1,60,True),("LAB_A",2,60,True),
                                  ("LAB_B",0,30,True),("LAB_B",2,60,False)]:
        r={"schema_version":1,"origin":"synthetic_fixture","source_id":source,"config_sha256":"a"*64,
           "minute":(minute(start)+timedelta(minutes=k)).isoformat(),
           "samples":[{"slot":i,"recent":recent,"fps":5.0 if recent else None,
                       "decode_receive_ms":i/10 if recent else None} for i in range(count)]}
        r["minute_sha256"]=fingerprint(r);records.append(r)
    return records,start,end,["LAB_A","LAB_B"]

def main():
    p=argparse.ArgumentParser();p.add_argument("--input");p.add_argument("--fixture",action="store_true");p.add_argument("--output",required=True);args=p.parse_args()
    require(bool(args.input)!=args.fixture,"choose one input")
    if args.fixture:values=fixture()
    else:
        path=Path(args.input);require(0<path.stat().st_size<=MAX_BYTES,"input size limit")
        data=json.loads(path.read_text(encoding="utf-8"));values=(data["records"],data["start"],data["end"],data["sources"])
    write_exclusive(args.output,build(*values))

if __name__=="__main__":main()
