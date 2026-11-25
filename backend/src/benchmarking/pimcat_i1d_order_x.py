"""Offline I1D matched-green-budget order ablation; never a controller."""
import argparse
import json
import math
import tempfile
from pathlib import Path
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking import si11d_sumo as d
from src.benchmarking import si11c_predictive_x as c
from src.benchmarking.si11b_robust_x import risk_profile
from src.optimization.engine import evaluate

SEEDS=tuple(range(14600,14604))
CANDIDATE="order_x"
POLICIES=(*d.POLICIES,CANDIDATE)


def forecast_cost(pair, action, ages, stress):
    first,w=action
    _,cost=c.forecast(tuple(p[0] for p in pair),pair,action,stress)
    return cost+2*max(ages[first],ages[1-first]+w+c.TRANSITION)


def select(policy,pair,queues,t,confidence=.95):
    if policy!=CANDIDATE:
        return c.select(policy,pair,queues,t,confidence)
    base,reason=c.select("demand_proportional",pair,queues,t,confidence)
    if base is None:
        return base,reason
    major,w=base
    minor=1-major
    p=c.current_pair(pair,queues)
    if not 0<p[minor][0]<p[major][0]:
        return base,"order_keep_empty_or_tie"
    result=evaluate(c.observed(pair,queues,t,confidence))
    assert result.origin=="synthetic_demo" and result.operational_decision=="abstain"
    assert not result.physical_actuation and not result.operationally_validated
    if (result.preferred_in_simulation=="abstain" or not result.minor_clearance_feasible
            or p[minor][0]>result.dynamic_x_safe_vehicles):
        return base,"order_keep_x_veto"
    alt=(minor,c.SERVICE-w)
    if not any(r["window"]==alt[1] and r["eligible"] for r in risk_profile(p[minor],p[major])):
        return base,"order_keep_risk_veto"
    ages=[max((t-b for b in q),default=0) for q in queues]
    if ages[major]+alt[1]+c.TRANSITION>180:
        return base,"order_keep_wait_veto"
    for stress in (0.,.05):
        original=forecast_cost(p,base,ages,stress)
        alternate=forecast_cost(p,alt,ages,stress)
        if original<=0 or alternate>.95*original:
            return base,"order_keep_cost_veto"
    assert alt[1]+base[1]==c.SERVICE
    return alt,"order_minor_first"


def summarize(rows):
    original=d.summarize(rows)
    means={p:{k:fmean(r["metrics"][p][k] for r in rows) for k in d.FIELDS} for p in POLICIES}
    m=means[CANDIDATE]
    checks={}
    for p in ("fixed_alternating","demand_proportional"):
        b=means[p]
        checks[p]={"queue_area_noninferiority_5pct":m[d.FIELDS[0]]<=1.05*b[d.FIELDS[0]],
                   "throughput_noninferiority_5pct":m[d.FIELDS[1]]>=.95*b[d.FIELDS[1]],
                   "uninserted_not_increased":m[d.FIELDS[2]]<=b[d.FIELDS[2]],
                   "pending_delay_not_increased":m[d.FIELDS[3]]<=b[d.FIELDS[3]],
                   "critical_exposure_not_increased":m[d.FIELDS[4]]<=b[d.FIELDS[4]],
                   "max_wait_noninferiority_5pct":m[d.FIELDS[5]]<=1.05*b[d.FIELDS[5]]}
    events={p:{k:sum(r["metrics"][p][k] for r in rows)
               for k in ("fallbacks","colliding_vehicle_events","teleports")} for p in POLICIES}
    reasons={}
    for r in rows:
        for plan in r["metrics"][CANDIDATE]["plans"]:
            k=plan["reason"];reasons[k]=reasons.get(k,0)+1
    def improvement(p):
        return m[d.FIELDS[0]]<means[p][d.FIELDS[0]] or m[d.FIELDS[4]]<means[p][d.FIELDS[4]]
    gates=improvement("fixed_alternating") and not any(events[CANDIDATE].values()) and all(
        not (x["colliding_vehicle_events"] or x["teleports"]) for x in events.values()) and all(all(x.values()) for x in checks.values())
    paired={}
    for p in d.POLICIES:
        paired[p]={}
        for k in d.FIELDS:
            diffs=[r["metrics"][CANDIDATE][k]-r["metrics"][p][k] for r in rows]
            paired[p][k]={"lower":sum(v<0 for v in diffs),"equal":sum(v==0 for v in diffs),
                          "higher":sum(v>0 for v in diffs),"mean_delta":fmean(diffs)}
    return {"cases":len(rows),"means":means,"original_si11d":original,"gates":checks,
            "events":events,"decision_reasons":reasons,"paired":paired,
            "improvement_vs_fixed":improvement("fixed_alternating"),
            "improvement_vs_proportional":improvement("demand_proportional"),
            "all_research_gates_met":gates}


def assess(rows):
    overall=summarize(rows)
    cohorts={k:summarize([r for r in rows if r["family"] in fs]) for k,fs in d.COHORTS.items()}
    families={f:summarize([r for r in rows if r["family"]==f]) for f in d.FAMILIES}
    passed=(all(v["all_research_gates_met"] for v in cohorts.values())
            and overall["improvement_vs_proportional"]
            and overall["decision_reasons"].get("order_minor_first",0)>0)
    return overall,cohorts,families,passed


def run():
    api=d.ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-i1d-") as folder:
        rows=[d.case(api,Path(folder)/f"{f}-{s}",f,s,POLICIES,select_fn=select)
              for f in d.FAMILIES for s in SEEDS]
    overall,cohorts,families,passed=assess(rows)
    report={"scope":"pimcat_i1d_matched_budget_order_synthetic_not_field","sumo_version":d.VERSION,
            "seeds":list(SEEDS),"policies":list(POLICIES),"cases":len(rows),
            "trajectories":len(rows)*len(POLICIES),"horizon_seconds":d.HORIZON,"rows":rows,
            "overall":overall,"cohorts":cohorts,"families":families,"research_gate_passed":passed,
            "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION",
            "candidate_promoted":False,"x_validated_for_real_traffic":False,
            "operationally_validated":False,"physical_actuation":False,
            "commercial_demo_authorized":False,"operational_decision":"abstain"}
    report["result_sha256"]=fingerprint(report)
    return report


def verify(report):
    r=dict(report);sha=r.pop("result_sha256");assert fingerprint(r)==sha
    assert r["scope"]=="pimcat_i1d_matched_budget_order_synthetic_not_field"
    assert r["sumo_version"]==d.VERSION and r["horizon_seconds"]==d.HORIZON
    assert r["seeds"]==list(SEEDS) and r["policies"]==list(POLICIES)
    assert r["cases"]==32 and r["trajectories"]==160
    rows=r["rows"]
    assert len(rows)==32 and {(x["family"],x["seed"]) for x in rows}=={(f,s) for f in d.FAMILIES for s in SEEDS}
    for x in rows:
        assert set(x["metrics"])==set(POLICIES)
        for p,m in x["metrics"].items():
            assert m["runtime_version"].split()[-1]==d.VERSION
            assert m["scheduled"]==x["scheduled"]==m["inserted"]+m["uninserted"]
            assert m["inserted"]==m["departed_network"]+m["remaining_network"]
            assert sum(m["green_ticks"])==c.SERVICE*c.CYCLES and min(m["green_ticks"])>=12*c.CYCLES
            assert len(m["plans"])==c.CYCLES
            assert not (m["colliding_vehicle_events"] or m["teleports"])
    a,b,f,g=assess(rows)
    assert r["overall"]==a and r["cohorts"]==b and r["families"]==f and r["research_gate_passed"]==g
    assert r["c3_independent_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"
    assert r["operational_decision"]=="abstain"
    assert all(r[k] is False for k in ("candidate_promoted","x_validated_for_real_traffic",
                                       "operationally_validated","physical_actuation","commercial_demo_authorized"))
    return g


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    report=run()
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({"gate":verify(report),"overall":report["overall"]},sort_keys=True))


if __name__=="__main__":main()
