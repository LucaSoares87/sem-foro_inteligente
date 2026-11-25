"""I1C: offline receiving-space pressure experiment; no runtime integration."""
import argparse
import json
import math
import tempfile
from pathlib import Path
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking import pimcat_e_global as e

SEEDS = tuple(range(13500, 13504))
CANDIDATES = {"receiving_pressure": "global_pressure", "receiving_storage": "global_storage"}
POLICIES = (*e.POLICIES, *CANDIDATES)


def receiving_context(graph, readings, j, t, available):
    if not available:
        return None
    moves = graph["movements"]
    result = {}
    for g, (origin, dest) in moves[j].items():
        before = [a for ms in moves.values() for a, b in ms.values() if b == origin]
        after = [b for ms in moves.values() for a, b in ms.values() if a == dest]
        keys = {origin, dest, *before, *after}
        if any(e.criticity(readings.get(k), t)[0] is None for k in keys):
            return None
        a, b = readings[origin], readings[dest]
        q, o = a.queue/a.capacity, b.count/b.capacity
        upstream = max((min(1, readings[k].queue/readings[k].capacity) for k in before), default=0)
        downstream = max((min(1, readings[k].count/readings[k].capacity) for k in after), default=0)
        space = max(0, 1-min(1, o))
        score = (q+.25*upstream)*space-o-.25*downstream
        result[g] = score-e.pressure(a,b)
    return result


def evaluate_case(api, root, family, seed):
    row = e.case(api, root, family, seed)
    alt = e.case(api, root, family, seed, tuple(CANDIDATES.values()),
                 context_fn=receiving_context,
                 snapshot_ticks=(175,240,305) if family=="outage" and seed==SEEDS[0] else ())
    assert all(row[k]==alt[k] for k in ("network_sha256","demand_sha256","graph","nodes","family","seed"))
    for p,b in CANDIDATES.items():
        row["metrics"][p] = alt["metrics"][b]
    return row


def paired(rows, candidate, baseline):
    out = {}
    for key in ("person_area","critical_exposure","critical_entries","vehicle_max_wait",
                "pedestrian_max_wait","vehicle_uninserted","vehicle_exited","mean_stops",
                "speed_cv","mean_travel_seconds"):
        diffs = [r["metrics"][candidate][key]-r["metrics"][baseline][key] for r in rows
                 if r["metrics"][candidate][key] is not None and r["metrics"][baseline][key] is not None]
        out[key] = {"comparable":len(diffs),"lower":sum(x<0 for x in diffs),
                    "equal":sum(x==0 for x in diffs),"higher":sum(x>0 for x in diffs),
                    "mean_delta":fmean(diffs) if diffs else None}
    return out


def assess(rows):
    groups = {"overall":rows,"two_columns":[r for r in rows if r["columns"]==2],
              "three_columns":[r for r in rows if r["columns"]==3],
              "stress":[r for r in rows if r["family"] in ("compact","deadlines","outage")]}
    summaries = {k:e.summary(v,POLICIES) for k,v in groups.items()}
    gates = {}
    for p,b in CANDIDATES.items():
        g = {}
        for k in ("two_columns","three_columns","stress"):
            s=summaries[k]; a,ref=s[p],s[b]
            orig=e.gate(s,p)
            extra={key:a[key]<=ref[key] for key in ("critical_exposure","critical_entries",
                "total_vehicle_deadline_violations","total_pedestrian_deadline_violations")}
            extra["person_area"]=a["person_area"]<=1.05*ref["person_area"]
            g[k]={"original_E_gate":orig,"additional":extra,
                  "passed":orig["passed"] and all(extra.values())}
        a,ref=summaries["overall"][p],summaries["overall"][b]
        g["improvement_vs_local"]=a["person_area"]<summaries["overall"]["local_demand"]["person_area"]
        g["strict_critical_improvement"]=a["critical_exposure"]<ref["critical_exposure"] or a["critical_entries"]<ref["critical_entries"]
        g["strict_spillback_prevention"]=a["total_critical_entries"]==0
        g["passed"]=g["improvement_vs_local"] and g["strict_critical_improvement"] and all(g[k]["passed"] for k in ("two_columns","three_columns","stress"))
        gates[p]=g
    return summaries,gates


def verify_case(row):
    assert row["conflicts_verified"] and set(row["metrics"])==set(POLICIES)
    for p,m in row["metrics"].items():
        assert m["runtime_version"].split()[-1]==e.VERSION
        assert m["vehicle_scheduled"]==m["vehicle_exited"]+m["vehicle_remaining"]+m["vehicle_uninserted"]
        assert m["pedestrian_scheduled"]==m["pedestrian_exited"]+m["pedestrian_remaining"]+m["pedestrian_uninserted"]
        assert m["pedestrian_admitted"]==m["pedestrian_completed"]+m["pedestrian_crossing"]
        assert math.isclose(m["critical_exposure"],sum(m["edge_critical_exposure"].values()),abs_tol=1e-7)
        assert not any(m[k] for k in ("collisions","teleports","overspeed_samples","conflict_violations","red_entries","rp07_empty_interruptions"))
        assert m["fallback_ticks"]==(180 if row["family"]=="outage" and (p.startswith("global") or p in CANDIDATES) else 0)
        if row["family"]=="outage":
            assert not any((180<=tick<300 or 420<=tick<480) and reason.endswith("P4_global")
                           for tick,j,phase,target,reason in m["plans"])
            if row["seed"]==SEEDS[0] and p in CANDIDATES:
                assert [s["tick"] for s in m["snapshots"]]==[175,240,305]
                assert all(x["level"]=="unknown" and x["index"] is None and x["count"] is None
                           for x in m["snapshots"][1]["edges"].values())
        if row["family"]=="rp07_single":
            assert m["midblock_completed"]==1


def run():
    api=e.ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-i1c-") as folder:
        rows=[evaluate_case(api,Path(folder)/f"{f}-{s}",f,s) for f in e.FAMILIES for s in SEEDS]
    summaries,gates=assess(rows)
    d={"scope":"pimcat_i1c_receiving_pressure_synthetic_not_field","sumo_version":e.VERSION,
       "cases":len(rows),"trajectories":len(rows)*len(POLICIES),"horizon_seconds":e.HORIZON,
       "seeds":list(SEEDS),"policies":list(POLICIES),"rows":rows,"summaries":summaries,
       "families":{f:e.summary([r for r in rows if r["family"]==f],POLICIES) for f in e.FAMILIES},
       "paired":{p:paired(rows,p,b) for p,b in CANDIDATES.items()},"gates":gates,
       "research_gate_passed":any(g["passed"] for g in gates.values()),
       "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","field_speed_calibration":"NOT_RUN",
       "emergency_validation":"NOT_RUN","physical_contingency_validation":"NOT_RUN",
       "candidate_promoted":False,"operationally_validated":False,"physical_actuation":False,
       "commercial_demo_authorized":False,"operational_decision":"abstain"}
    d["result_sha256"]=fingerprint(d)
    return d


def verify(report):
    d=dict(report); sha=d.pop("result_sha256")
    assert fingerprint(d)==sha
    assert d["scope"]=="pimcat_i1c_receiving_pressure_synthetic_not_field" and d["sumo_version"]==e.VERSION
    assert d["cases"]==24 and d["trajectories"]==144 and d["seeds"]==list(SEEDS) and d["policies"]==list(POLICIES)
    rows=d["rows"]
    assert len(rows)==24 and {(r["family"],r["seed"]) for r in rows}=={(f,s) for f in e.FAMILIES for s in SEEDS}
    for r in rows:verify_case(r)
    s,g=assess(rows)
    assert d["summaries"]==s and d["gates"]==g
    assert d["families"]=={f:e.summary([r for r in rows if r["family"]==f],POLICIES) for f in e.FAMILIES}
    assert d["paired"]=={p:paired(rows,p,b) for p,b in CANDIDATES.items()}
    assert d["research_gate_passed"]==any(x["passed"] for x in g.values())
    assert d["c3_independent_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"
    assert all(d[k]=="NOT_RUN" for k in ("field_speed_calibration","emergency_validation","physical_contingency_validation"))
    assert d["operational_decision"]=="abstain"
    assert all(d[k] is False for k in ("candidate_promoted","operationally_validated","physical_actuation","commercial_demo_authorized"))
    return g


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    report=run()
    with (root/"study.json").open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps(verify(report),sort_keys=True))
    print(json.dumps(report["paired"],sort_keys=True))
    row=next(r for r in report["rows"] if r["family"]=="outage" and r["seed"]==SEEDS[0])
    for p in CANDIDATES:
        for snap in row["metrics"][p]["snapshots"]:
            e.render_svg(row["graph"],snap,root/f"{p}-{snap['tick']}.svg")


if __name__=="__main__":main()
