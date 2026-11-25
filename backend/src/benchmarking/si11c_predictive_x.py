"""Research-only, discrete FIFO evaluation; no traffic controller interface."""
import argparse
import json
import math
from collections import deque
from itertools import product
from functools import lru_cache
from pathlib import Path
from random import Random
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking.si11_counterfactual import FAMILIES, snapshot
from src.benchmarking.si11b_robust_x import NOVEL, choose as robust_choose, risk_profile
from src.optimization.engine import evaluate
from src.queueing.contracts import QueueSnapshot

CYCLE=60
CYCLES=4
TRANSITION=4
SERVICE=CYCLE-2*TRANSITION
WINDOWS=(12,20,26,32,40)
ACTIONS=tuple(product((0,1),WINDOWS))
SEEDS=tuple(range(3000,3020))
REPLICATION={k:FAMILIES[k] for k in ("light_asymmetric","balanced","dominant_growth",
    "feasible_near_boundary","burst_uncertainty","minor_no_net_clearance")}
REPLICATION.update({k:NOVEL[k] for k in ("tight_storage","slow_discharge")})
NOVEL_SHIFT={
    "low_asymmetric":((2,.07,.82,26),(8,.18,.76,36)),
    "storage_asymmetric":((3,.19,.72,22),(16,.32,.78,25)),
    "near_balance_shift":((9,.29,.72,35),(11,.27,.75,34)),
    "arrival_regime_shift":((3,.18,.75,26),(12,.28,.78,33)),
    "correlated_bursts":((4,.16,.72,24),(11,.30,.80,30)),
    "service_outage":((4,.18,.70,24),(13,.30,.75,35)),
    "oversaturation_shift":((5,.32,.60,30),(17,.43,.70,38)),
    "empty_shift":((0,0.,.75,25),(0,0.,.80,25)),
}
POLICIES=("fixed_alternating","demand_proportional","original_x","robust_x","predictive_x","predictive_no_x")
METRICS=("queue_area_vehicle_seconds","departed","remaining","max_wait_seconds",
         "critical_exposure_vehicle_seconds","overflow_exposure_vehicle_seconds","peak_queue")


def schedule(action):
    first,w=action
    if first not in (0,1) or type(w) is not int or not 12<=w<=40:
        raise ValueError("invalid synthetic action")
    return (first,)*w+(None,)*TRANSITION+(1-first,)*(SERVICE-w)+(None,)*TRANSITION


def streams(pair,seed,family):
    rng=Random(seed)
    arrivals=[[],[]]; services=[[],[]]
    for t in range(CYCLE*CYCLES):
        for g,(_,a,s,_) in enumerate(pair):
            if family in ("burst_uncertainty","correlated_bursts"):
                a*=1.8 if t%20<10 else .2
            if family=="arrival_regime_shift":
                a*=1.5 if (t//CYCLE+g)%2==0 else .5
            if family=="service_outage" and t%60<15:
                s*=.30
            arrivals[g].append(int(rng.random()<min(1.,a)))
            services[g].append(int(rng.random()<s))
    return arrivals,services


def observed(pair,queues,t,confidence=.95):
    base=snapshot(pair,confidence).model_dump()
    for g,(q,row) in enumerate(zip(queues,base["approaches"])):
        n=len(q)
        if n>200:
            raise ValueError("synthetic queue outside snapshot contract")
        ages=[t-b for b in q]
        row.update(queue_length=n,visible_vehicles=n,stopped_ratio=float(n>0),
            mean_wait_seconds=fmean(ages) if ages else 0.,
            max_wait_seconds=max(ages,default=0),
            storage_occupancy_ratio=min(2.,n/pair[g][3]),
            spillback_margin_ratio=max(0.,1-n/pair[g][3]))
    return QueueSnapshot.model_validate(base)


def current_pair(pair,queues):
    return tuple((len(q),*p[1:]) for p,q in zip(pair,queues))


def forecast(q,pair,action,stress):
    """Independent fluid forecast; actual evaluation uses integer FIFO."""
    a=[min(1.,p[1]+stress) for p in pair]
    s=[max(0.,p[2]-stress) for p in pair]
    caps=[p[3] for p in pair]
    q=list(q); area=critical=overflow=imbalance=0.
    for active in schedule(action):
        for g in (0,1):
            q[g]=max(0.,q[g]+a[g]-(s[g] if active==g else 0.))
        area+=sum(q)
        critical+=sum(max(0.,q[g]-.85*caps[g]) for g in (0,1))
        overflow+=sum(max(0.,q[g]-caps[g]) for g in (0,1))
        imbalance+=abs(q[0]/caps[0]-q[1]/caps[1])
    return tuple(q),area+4*critical+15*overflow+imbalance


@lru_cache(maxsize=2048)
def admissible(pair,major,restrict):
    if not restrict:
        return ACTIONS
    minor=1-major
    profile=risk_profile(pair[minor],pair[major])
    eligible={p["window"] for p in profile if p["eligible"]}
    return tuple(a for a in ACTIONS if a[0]==major or a[1] in eligible)


def predictive(pair,major,restrict=True):
    """Two-cycle receding-horizon beam search, no realized future arrivals."""
    starts=tuple(p[0] for p in pair)
    scenarios=(0.,.05)
    first=[]
    for action in admissible(pair,major,restrict):
        outcomes=[forecast(starts,pair,action,m) for m in scenarios]
        score=fmean(c+6*sum(q) for q,c in outcomes)
        first.append((score,action,outcomes))
    finalists=sorted(first,key=lambda x:(x[0],x[1][0]!=major,x[1][1]))[:3]
    best=None
    for _,action,outcomes in finalists:
        # The second plan is shared across the two forecast scenarios.
        # Require its minor-first X gate in both predicted states.
        sets=[]
        for q,_ in outcomes:
            p=tuple((math.ceil(q[g]),*pair[g][1:]) for g in (0,1))
            m=max((0,1),key=lambda g:(p[g][0],p[g][0]/p[g][3],p[g][1],g))
            sets.append(set(admissible(p,m,restrict)))
        common=sets[0]&sets[1]
        if not common:
            # No joint second-step action: reject this first-step plan.
            continue
        for next_action in sorted(common):
            costs=[]
            for stress,(q,c) in zip(scenarios,outcomes):
                end,next_cost=forecast(q,pair,next_action,stress)
                costs.append(c+next_cost+6*sum(end))
            key=(fmean(costs),action[0]!=major,action[1],next_action)
            if best is None or key<best[0]:
                best=(key,action)
    # Explicit research abstention if the lookahead has no common admissible action.
    return None if best is None else best[1]


def select(policy,pair,queues,t,confidence=.95):
    state=observed(pair,queues,t,confidence)
    original=evaluate(state)
    if (original.origin!="synthetic_demo" or original.operational_decision!="abstain"
            or original.physical_actuation or original.operationally_validated):
        raise AssertionError("operational boundary violated")
    if original.preferred_in_simulation=="abstain":
        return None, "low_confidence_abstain"
    major=int(original.major_group.group_id=="B")
    minor=1-major
    p=current_pair(pair,queues)
    fixed=(t//CYCLE%2,26)
    if policy=="fixed_alternating":
        return fixed,"fixed"
    if policy=="demand_proportional":
        demand=[(x[0]+CYCLE*x[1])/max(.05,x[2]) for x in p]
        first=major
        w=SERVICE*demand[first]/max(1e-9,sum(demand))
        return (first,max(12,min(40,round(w)))),"proportional"
    if policy in ("predictive_x","predictive_no_x"):
        action=predictive(p,major,policy=="predictive_x")
        return action,"predictive" if action else "no_common_forecast_action"
    if policy not in ("original_x","robust_x"):
        raise ValueError("unknown policy")
    w=math.ceil(original.minor_first.analysis_first_window_seconds) if original.minor_first else 28
    pref=original.preferred_in_simulation
    if policy=="robust_x":
        candidate=robust_choose(p,original)
        pref=candidate["preference"]
        if candidate["window"] is not None:
            w=candidate["window"]
    if pref not in ("minor_first","major_first"):
        return fixed,"no_material_advantage_fixed"
    return (minor if pref=="minor_first" else major,max(12,min(40,w))),pref


def simulate(policy,pair,arrivals,services):
    queues=[deque([0]*p[0]) for p in pair]
    area=departed=critical=overflow=peak=max_wait=0
    fallbacks=0; plans=[]; served=[0,0]
    for start in range(0,CYCLE*CYCLES,CYCLE):
        action,reason=select(policy,pair,queues,start)
        if action is None:
            fallbacks+=1
            action=(start//CYCLE%2,26) # evaluation-only fallback, not a controller recommendation
        plans.append({"first":action[0],"window":action[1],"reason":reason})
        for offset,active in enumerate(schedule(action)):
            t=start+offset
            if active is not None:
                served[active]+=1
            for g,q in enumerate(queues):
                q.extend([t]*arrivals[g][t])
                if active==g and q and services[g][t]:
                    max_wait=max(max_wait,t-q.popleft())
                    departed+=1
                if q:
                    max_wait=max(max_wait,t+1-q[0])
                critical+=max(0.,len(q)-.85*pair[g][3])
                overflow+=max(0,len(q)-pair[g][3])
            n=sum(map(len,queues))
            area+=n; peak=max(peak,n)
    remaining=sum(map(len,queues)); incoming=sum(map(sum,arrivals))
    assert sum(p[0] for p in pair)+incoming==departed+remaining
    assert sum(served)==SERVICE*CYCLES and min(served)>=12*CYCLES
    return {"queue_area_vehicle_seconds":area,"departed":departed,"remaining":remaining,
        "max_wait_seconds":max_wait,"critical_exposure_vehicle_seconds":critical,
        "overflow_exposure_vehicle_seconds":overflow,"peak_queue":peak,"arrivals":incoming,
        "service_opportunity_ticks":served,"fallbacks":fallbacks,"plans":plans}


def case(cohort,family,pair,seed):
    if seed%2:
        pair=pair[::-1]
    a,s=streams(pair,seed,family)
    return {"cohort":cohort,"family":family,"seed":seed,"pair":pair,
        "stream_sha256":fingerprint({"arrivals":a,"services":s}),
        "metrics":{p:simulate(p,pair,a,s) for p in POLICIES}}


def summarize(rows):
    means={p:{m:fmean(r["metrics"][p][m] for r in rows) for m in METRICS} for p in POLICIES}
    candidate=means["predictive_x"]
    gates={}
    for p in ("original_x","robust_x","demand_proportional","fixed_alternating"):
        base=means[p]
        gates[p]={"queue_area_noninferiority_5pct":candidate["queue_area_vehicle_seconds"]<=1.05*base["queue_area_vehicle_seconds"],
            "departures_noninferiority_5pct":candidate["departed"]>=.95*base["departed"],
            "critical_exposure_not_increased":candidate["critical_exposure_vehicle_seconds"]<=base["critical_exposure_vehicle_seconds"],
            "overflow_not_increased":candidate["overflow_exposure_vehicle_seconds"]<=base["overflow_exposure_vehicle_seconds"],
            "max_wait_noninferiority_5pct":candidate["max_wait_seconds"]<=1.05*base["max_wait_seconds"]}
    fallback=sum(r["metrics"]["predictive_x"]["fallbacks"] for r in rows)
    improvement=candidate["queue_area_vehicle_seconds"]<means["original_x"]["queue_area_vehicle_seconds"] or candidate["critical_exposure_vehicle_seconds"]<means["original_x"]["critical_exposure_vehicle_seconds"]
    return {"cases":len(rows),"means":means,"gates":gates,"predictive_fallbacks":fallback,
        "material_directional_improvement_vs_original":improvement,
        "all_research_gates_met":fallback==0 and improvement and all(all(g.values()) for g in gates.values())}


def run():
    pair=REPLICATION["light_asymmetric"]
    qs=[deque([0]*p[0]) for p in pair]
    assert select("predictive_x",pair,qs,0,.64)[0] is None
    cohorts={"replication_new_seeds":REPLICATION,"novel_shift":NOVEL_SHIFT}
    rows=[case(c,f,p,s) for c,fs in cohorts.items() for f,p in fs.items() for s in SEEDS]
    summaries={c:summarize([r for r in rows if r["cohort"]==c]) for c in cohorts}
    result={"schema_version":1,"scope":"synthetic_multicycle_not_field","seeds":list(SEEDS),
        "cycle_seconds":CYCLE,"cycles":CYCLES,"transition_ticks_per_cycle":2*TRANSITION,
        "overall":summarize(rows),"cohorts":summaries,
        "families":{f:summarize([r for r in rows if r["family"]==f]) for fs in cohorts.values() for f in fs},
        "cases":rows,"research_gate_passed":all(v["all_research_gates_met"] for v in summaries.values()),
        "low_confidence_abstention_verified":True,"sumo_validation":"NOT_RUN",
        "candidate_promoted":False,"x_validated_for_real_traffic":False,"commercial_demo_authorized":False,
        "operationally_validated":False,"physical_actuation":False}
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
