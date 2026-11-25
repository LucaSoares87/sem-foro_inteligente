"""Offline synthetic research. No operational integration, timing recommendation or actuation."""
import argparse
import json
import math
from pathlib import Path
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking.si11_counterfactual import FAMILIES, exogenous, simulate, snapshot
from src.optimization.engine import evaluate

# Registered before executing new scenarios. These are assumptions, not calibrated bounds.
RISK=.05
RATE_MARGIN=.05
MAX_WINDOW=30
TRANSITION=4
STORAGE_RATIO=.85
SEEDS=tuple(range(1000,1040))
NOVEL={
    "sparse_asymmetric":((1,.04,.80,20),(9,.22,.75,36)),
    "moderate_asymmetric":((4,.18,.78,26),(13,.28,.74,38)),
    "tight_storage":((2,.12,.70,20),(17,.35,.80,24)),
    "bursty_tight":((3,.16,.72,24),(14,.43,.78,26)),
    "slow_discharge":((4,.25,.40,30),(10,.22,.70,36)),
    "near_saturation":((5,.38,.55,24),(19,.53,.72,32)),
    "balanced_novel":((8,.22,.70,32),(9,.26,.72,32)),
    "low_demand":((0,.03,.75,20),(3,.08,.76,28)),
}
POLICIES=("original_x","robust_x","fixed_a","fixed_b","major_first","minor_first")
FIELDS=("queue_area_vehicle_seconds","departed","remaining","max_observed_wait_seconds",
        "critical_exposure_vehicle_seconds","overflow_exposure_vehicle_seconds","peak_combined_queue")


def step(dist, probabilities):
    out={}
    for state,mass in dist.items():
        for increment,prob in probabilities:
            if prob:
                out[state+increment]=out.get(state+increment,0.)+mass*prob
    return out


def risk_profile(minor,major):
    """Exact discrete iid stress distributions; no realized future arrivals used.

    X(window) is a lower quantile of cumulative net service opportunities.
    Net >= initial queue is sufficient for clearing at least once by window end,
    not for remaining empty. Major arrivals are nonnegative before its service.
    """
    q,ar,sr,cap=minor
    mq,ma,_,mc=major
    ar=min(1.,ar+RATE_MARGIN)
    sr=max(0.,sr-RATE_MARGIN)
    ma=min(1.,ma+RATE_MARGIN)
    headroom=math.floor(STORAGE_RATIO*mc)-mq
    arrivals={0:1.}
    net={0:1.}
    risks={}
    for t in range(1,MAX_WINDOW+TRANSITION+1):
        arrivals=step(arrivals,((0,1-ma),(1,ma)))
        risks[t]=sum(m for k,m in arrivals.items() if k>headroom)
    profile=[]
    for t in range(1,MAX_WINDOW+1):
        net=step(net,((-1,ar*(1-sr)),(0,ar*sr+(1-ar)*(1-sr)),(1,(1-ar)*sr)))
        major_risk=risks[t+TRANSITION]
        feasible_counts=[k for k in range(0,min(t,math.floor(STORAGE_RATIO*cap))+1)
                         if sum(m for n,m in net.items() if n>=k)>=1-RISK-1e-12]
        x=max(feasible_counts,default=0)
        clear_prob=sum(m for n,m in net.items() if n>=q)
        eligible=major_risk<=RISK+1e-12 and clear_prob>=1-RISK-1e-12 and q<=x
        profile.append({"window":t,"x":x if major_risk<=RISK+1e-12 else 0,
                        "major_critical_probability_assumed":major_risk,
                        "minor_clearance_lower_probability_assumed":clear_prob,"eligible":eligible})
    return profile


def choose(pair,result):
    """Veto or re-time only original minor-first choices; never promotes other cases."""
    if result.origin!="synthetic_demo" or result.operational_decision!="abstain" or result.physical_actuation:
        raise ValueError("synthetic-only input required")
    if result.preferred_in_simulation=="abstain":
        return {"preference":"abstain","reason":"original_abstention","x":None,"window":None,"selected":None}
    if result.preferred_in_simulation!="minor_first":
        return {"preference":result.preferred_in_simulation,"reason":"original_non_minor_preserved",
                "x":None,"window":None,"selected":None}
    g={"A":pair[0],"B":pair[1]}
    minor=g[result.minor_group.group_id]
    major=g[result.major_group.group_id]
    profile=risk_profile(minor,major)
    x=max(p["x"] for p in profile)
    eligible=next((p for p in profile if p["eligible"]),None)
    if eligible is None:
        return {"preference":"major_first","reason":"uncertainty_veto","x":x,"window":None,"selected":None}
    return {"preference":"minor_first","reason":"assumed_probability_gate","x":x,
            "window":eligible["window"],"selected":eligible}


def case(cohort,family,pair,seed):
    if seed%2:
        pair=pair[::-1]
    original=evaluate(snapshot(pair))
    if original.operational_decision!="abstain" or original.operationally_validated or original.physical_actuation:
        raise AssertionError("operational boundary violated")
    candidate=choose(pair,original)
    if candidate["preference"]=="abstain":
        raise AssertionError("unexpected abstention in high-confidence synthetic study")
    major,minor=original.major_group.group_id,original.minor_group.group_id
    window=math.ceil(original.minor_first.analysis_first_window_seconds) if original.minor_first else 28
    plans={"fixed_a":("A",28),"fixed_b":("B",28),"minor_first":(minor,window),"major_first":(major,window)}
    pref=original.preferred_in_simulation
    plans["original_x"]=plans[pref] if pref in ("minor_first","major_first") else plans["fixed_a"]
    plans["robust_x"]=(minor,candidate["window"]) if candidate["preference"]=="minor_first" else (
        plans["major_first"] if candidate["reason"]=="uncertainty_veto" else plans["original_x"])
    arrivals,services=exogenous(pair,seed,family in ("burst_uncertainty","bursty_tight"))
    metrics={k:simulate(pair,arrivals,services,*plan) for k,plan in plans.items()}
    return {"cohort":cohort,"family":family,"seed":seed,"pair":pair,"original_preference":pref,
        "original_x":original.dynamic_x_safe_vehicles,"original_window":window,
        "candidate":candidate,"metrics":metrics}


def summary(rows):
    means={p:{f:fmean(r["metrics"][p][f] for r in rows) for f in FIELDS} for p in POLICIES}
    selected={}
    for p in ("original_x","robust_x"):
        chosen=[r for r in rows if (r["original_preference"] if p=="original_x" else r["candidate"]["preference"])=="minor_first"]
        exceed=sum(r["metrics"][p]["second_group_critical_before_service"] for r in chosen)
        selected[p]={"chosen_minor":len(chosen),"critical_before_major_service":exceed,
                     "conditional_rate":exceed/len(chosen) if chosen else None,
                     "unconditional_rate":exceed/len(rows)}
    base,rob=means["original_x"],means["robust_x"]
    orig,new=selected["original_x"],selected["robust_x"]
    coverage=new["chosen_minor"]/orig["chosen_minor"] if orig["chosen_minor"] else None
    gate={
        "conditional_critical_rate_at_most_5pct":new["conditional_rate"] is not None and new["conditional_rate"]<=.05,
        "critical_count_reduced":new["critical_before_major_service"]<orig["critical_before_major_service"],
        "at_least_half_minor_choices_retained":coverage is not None and coverage>=.5,
        "queue_area_noninferiority_5pct":rob["queue_area_vehicle_seconds"]<=1.05*base["queue_area_vehicle_seconds"],
        "departures_noninferiority_5pct":rob["departed"]>=.95*base["departed"],
        "total_critical_exposure_not_increased":rob["critical_exposure_vehicle_seconds"]<=base["critical_exposure_vehicle_seconds"],
        "total_overflow_exposure_not_increased":rob["overflow_exposure_vehicle_seconds"]<=base["overflow_exposure_vehicle_seconds"],
    }
    return {"cases":len(rows),"means":means,"minor_choice_outcomes":selected,
        "minor_choice_retention":coverage,"vetoes":sum(r["candidate"]["reason"]=="uncertainty_veto" for r in rows),
        "queue_area_wins_vs_original":sum(r["metrics"]["robust_x"]["queue_area_vehicle_seconds"]<r["metrics"]["original_x"]["queue_area_vehicle_seconds"] for r in rows),
        "queue_area_losses_vs_original":sum(r["metrics"]["robust_x"]["queue_area_vehicle_seconds"]>r["metrics"]["original_x"]["queue_area_vehicle_seconds"] for r in rows),
        "research_gates":gate,"all_research_gates_met":all(gate.values())}


def run():
    low=choose(FAMILIES["light_asymmetric"],evaluate(snapshot(FAMILIES["light_asymmetric"],.64)))
    assert low["preference"]=="abstain" and low["x"] is None and low["window"] is None
    cohorts={"familiar_new_seeds":FAMILIES,"novel_families":NOVEL}
    rows=[case(c,f,p,s) for c,fs in cohorts.items() for f,p in fs.items() for s in SEEDS]
    summaries={c:summary([r for r in rows if r["cohort"]==c]) for c in cohorts}
    result={"schema_version":1,"scope":"synthetic_robust_x_not_field","seeds":list(SEEDS),
        "assumptions":{"iid_bernoulli":True,"risk_per_constraint":RISK,"absolute_rate_margin":RATE_MARGIN,
                       "not_calibrated":True,"joint_failure_union_bound_under_assumptions":2*RISK},
        "overall":summary(rows),"cohorts":summaries,
        "families":{f:summary([r for r in rows if r["family"]==f]) for fs in cohorts.values() for f in fs},
        "cases":rows,"low_confidence_abstention_verified":True,
        "research_gate_passed":all(v["all_research_gates_met"] for v in summaries.values()),
        "candidate_promoted":False,"x_validated_for_real_traffic":False,
        "commercial_demo_authorized":False,"operationally_validated":False,"physical_actuation":False}
    result["result_sha256"]=fingerprint(result)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    a=p.parse_args()
    with Path(a.output).open("x",encoding="utf-8") as f:
        json.dump(run(),f,sort_keys=True,indent=2,allow_nan=False)


if __name__=="__main__":
    main()
