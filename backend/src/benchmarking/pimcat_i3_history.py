"""Offline, read-only longitudinal descriptions of F daily exports."""
import argparse
from datetime import date,timedelta
import json
import math
from pathlib import Path
from src.archive.store import fingerprint
from src.reporting.daily import bounds, ZONE

KEY=("source_id","line_id","direction","analytics_epoch","geometry_sha256","model_sha256","purpose")
MAX_DAYS=31
MAX_BYTES=8*1024*1024

def require(ok,message):
    if not ok:raise ValueError(message)

def nonnegative(x):
    return type(x) in (int,float) and math.isfinite(x) and x>=0

def validate(report):
    data=dict(report);digest=data.pop("report_sha256",None)
    require(digest==fingerprint(data),"report hash mismatch")
    require(data["schema_version"]==1 and data["timezone"]==ZONE and data["scope"]=="configured_sources_only","unsupported F report")
    require(data["origin"]=="observed_analytics_source_origin_unverified","invalid origin")
    require(all(data[k] is False for k in ("aggregation_across_sources","extrapolated","operationally_validated","physical_actuation","candidate_promoted")) and data["operational_decision"]=="abstain","invalid boundaries")
    require(data["unique_vehicles"] is None and data["network_total"] is None,"unsupported totals")
    require(all(v["value"] is None for v in data["unavailable_metrics"].values()),"unsupported field metric")
    day=date.fromisoformat(data["date"]);start,end=bounds(day)
    require(data["interval_start"]==start.isoformat() and data["interval_end"]==end.isoformat() and data["day_seconds"]==(end-start).total_seconds(),"invalid civil interval")
    require(isinstance(data["intersection_code"],str) and bool(data["intersection_code"]),"invalid intersection")
    sources=[x["source_id"] for x in data["sources"]]
    require(len(sources)<=32 and len(set(sources))==len(sources),"invalid sources")
    indexed={}
    for s in data["series"]:
        key=tuple(s[k] for k in KEY)
        require(all(isinstance(x,str) and x for x in key) and key[0] in sources and key[2] in ("negative_to_positive","positive_to_negative"),"invalid series")
        require(key not in indexed,"duplicate series")
        for group in ("observed","limited"):
            v=s[group]
            require(type(v["windows"]) is int and v["windows"]>=0 and nonnegative(v["seconds"]),"invalid window totals")
            require((v["windows"]==0 and v["seconds"]==0 and v["passages"] is None) or (v["windows"]>0 and v["seconds"]>0 and type(v["passages"]) is int and v["passages"]>=0),"invalid passages")
        total=s["observed"]["seconds"]+s["limited"]["seconds"]
        require(0<total<=data["day_seconds"] and math.isclose(s["coverage_fraction"],total/data["day_seconds"],rel_tol=0,abs_tol=1e-12) and math.isclose(s["unobserved_seconds"],data["day_seconds"]-total,rel_tol=0,abs_tol=1e-6),"invalid coverage")
        indexed[key]=s
    require(data["state"]==("available" if indexed else "empty"),"invalid report state")
    return day,indexed

def compare(left,right,seconds_l,seconds_r):
    result={"previous_passages_per_hour":None,"current_passages_per_hour":None,"difference_per_hour":None,"percent_change":None}
    if left is None or right is None:return {**result,"reason":"series_missing_or_lineage_changed"}
    if any(s["limited"]["windows"] for s in (left,right)):return {**result,"reason":"limited_quality"}
    if any(s["observed"]["seconds"]!=n for s,n in ((left,seconds_l),(right,seconds_r))):return {**result,"reason":"partial_coverage"}
    a=left["observed"]["passages"]*3600/seconds_l;b=right["observed"]["passages"]*3600/seconds_r
    return {"previous_passages_per_hour":a,"current_passages_per_hour":b,"difference_per_hour":b-a,
            "percent_change":(b-a)/a*100 if a>0 else None,"reason":"descriptive_only" if a>0 else "zero_previous_denominator"}

def build(reports):
    require(1<=len(reports)<=MAX_DAYS,"invalid report count")
    entries=[]
    for r in reports:
        day,index=validate(r);entries.append((day,r,index))
    entries.sort(key=lambda x:x[0])
    require(len({e[0] for e in entries})==len(entries),"duplicate date")
    require(len({e[1]["intersection_code"] for e in entries})==1,"mixed intersections")
    require((entries[-1][0]-entries[0][0]).days<MAX_DAYS,"date span limit")
    by_day={e[0]:e for e in entries};comparisons=[];missing=[];suggestions=[]
    for n in range((entries[-1][0]-entries[0][0]).days+1):
        d=entries[0][0]+timedelta(days=n)
        if d not in by_day:missing.append(d.isoformat())
        if n==0:continue
        a=by_day.get(d-timedelta(days=1));b=by_day.get(d)
        if a is None or b is None:continue
        for key in sorted(set(a[2])|set(b[2])):
            v=compare(a[2].get(key),b[2].get(key),a[1]["day_seconds"],b[1]["day_seconds"])
            comparisons.append({"previous_date":a[0].isoformat(),"current_date":b[0].isoformat(),"series":dict(zip(KEY,key)),**v})
    hashes=[{"date":d.isoformat(),"report_sha256":r["report_sha256"]} for d,r,_ in entries]
    reasons=sorted({x["reason"] for x in comparisons if x["reason"] in ("partial_coverage","limited_quality","series_missing_or_lineage_changed")}|({"missing_day"} if missing else set()))
    for reason in reasons:
        suggestions.append({"version":1,"kind":"research_data_quality_only","reason":reason,"evidence_sha256":fingerprint({"inputs":hashes,"reason":reason}),"parameter_application":False})
    result={"schema_version":1,"scope":"offline_F_descriptive_history_not_field","intersection_code":entries[0][1]["intersection_code"],
            "inputs":hashes,"missing_dates":missing,"comparisons":comparisons,"suggestions":suggestions,
            "aggregation_across_sources":False,"extrapolated":False,"unique_vehicles":None,"network_total":None,
            "physical_speed":None,"camera_availability":None,"counterfactual_improvement":None,"network_criticity":None,
            "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","field_speed_calibration":"NOT_RUN","soak_24h":"NOT_RUN",
            "candidate_promoted":False,"operationally_validated":False,"physical_actuation":False,"commercial_demo_authorized":False,"operational_decision":"abstain"}
    result["result_sha256"]=fingerprint(result)
    return result

def write_private(path,result):
    path=Path(path)
    with path.open("x",encoding="utf-8") as f:json.dump(result,f,sort_keys=True,indent=2,allow_nan=False)

def main():
    p=argparse.ArgumentParser();p.add_argument("--input",nargs="+",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    require(1<=len(a.input)<=MAX_DAYS,"invalid input count")
    reports=[]
    for name in a.input:
        path=Path(name);require(0<path.stat().st_size<=MAX_BYTES,"input size limit")
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    write_private(a.output,build(reports))

if __name__=="__main__":main()
