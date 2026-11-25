"""Synthetic offline research. Never controls signals or recommends field timings."""
import argparse
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from statistics import fmean
from uuid import UUID

from src.archive.store import fingerprint
from src.optimization.engine import evaluate
from src.queueing.contracts import QueueSnapshot, QueueApproachState

HORIZON=60
TRANSITION=4
SEEDS=tuple(range(100,140))
# Pre-registered synthetic group pairs: queue, arrivals/s, service opportunities/s, storage.
FAMILIES={
    "light_asymmetric":((2,.10,.65,24),(12,.30,.70,40)),
    "balanced":((7,.25,.65,30),(8,.25,.65,30)),
    "dominant_growth":((3,.12,.75,24),(18,.60,.75,30)),
    "near_storage":((4,.20,.65,24),(23,.30,.70,28)),
    "feasible_near_boundary":((3,.15,.65,24),(15,.50,.75,24)),
    "minor_no_net_clearance":((5,.65,.45,25),(12,.20,.70,40)),
    "burst_uncertainty":((3,.20,.70,24),(15,.35,.70,32)),
    "empty":((0,0.,.70,24),(0,0.,.70,32)),
}
POLICIES=("fixed_a","fixed_b","minor_first","major_first","dynamic_x")


def snapshot(pair,confidence=.95):
    approaches=[]
    for group,(q,arrival,service,capacity) in zip(("A","B"),pair):
        approaches.append(QueueApproachState(approach_id=group,service_group=group,
            visible_vehicles=q,queue_length=q,stopped_ratio=float(q>0),
            arrival_rate_vps=arrival,discharge_rate_vps=service,
            queue_growth_vps=arrival-service,mean_wait_seconds=0.,max_wait_seconds=0.,
            storage_capacity_vehicles=capacity,storage_occupancy_ratio=q/capacity,
            spillback_margin_ratio=max(0.,1-q/capacity),observation_confidence=confidence,
            visibility_calibrated=False,quality="experimental"))
    uid=UUID(int=1)
    return QueueSnapshot(source_id="SI11_SYNTHETIC",intersection_code="SI11_SYNTHETIC",
        session_id=uid,tracking_epoch=uid,analytics_epoch=uid,queue_epoch=uid,
        geometry_sha256="a"*64,model_sha256="b"*64,purpose="validation_only",
        data_origin="synthetic_demo",commercial_demo_authorized=False,frame_sequence=1,
        received_at=datetime(2020,1,1,tzinfo=timezone.utc),approaches=tuple(approaches))


def exogenous(pair,seed,burst=False):
    """Common random arrivals and service opportunities, generated before policy selection."""
    rng=Random(seed)
    arrivals={g:[] for g in ("A","B")}
    services={g:[] for g in ("A","B")}
    for g,(_,rate,service,_) in zip(("A","B"),pair):
        for tick in range(HORIZON):
            # Burst scenario keeps the same expected arrivals but concentrates them in time.
            p=rate
            if burst:
                p=rate*(1.8 if tick%20<10 else .2)
            arrivals[g].append(int(rng.random()<p))
            services[g].append(int(rng.random()<service))
    return arrivals,services


def simulate(pair,arrivals,services,first,window):
    """FIFO integer vehicles, independent of production cost function.
    Overflow is an exposure measure; no physical blocking model or dropped arrivals.
    """
    if first not in ("A","B") or type(window) is not int or not 1<=window<=HORIZON-TRANSITION:
        raise ValueError("invalid synthetic sequence")
    second="B" if first=="A" else "A"
    queues={g:deque([0]*p[0]) for g,p in zip(("A","B"),pair)}
    capacity={g:p[3] for g,p in zip(("A","B"),pair)}
    total_arrivals=total_departed=area=0
    peak= sum(map(len,queues.values()))
    max_wait=0
    critical=overflow=0.
    second_critical_during_first=False
    for tick in range(HORIZON):
        active=first if tick<window else None if tick<window+TRANSITION else second
        for g in ("A","B"):
            incoming=arrivals[g][tick]
            total_arrivals+=incoming
            queues[g].extend([tick]*incoming)
            if active==g:
                for _ in range(min(len(queues[g]),services[g][tick])):
                    birth=queues[g].popleft()
                    max_wait=max(max_wait,tick-birth)
                    total_departed+=1
            if queues[g]:
                max_wait=max(max_wait,tick+1-queues[g][0])
            critical+=max(0.,len(queues[g])-.85*capacity[g])
            overflow+=max(0,len(queues[g])-capacity[g])
        if tick<window+TRANSITION and len(queues[second])>.85*capacity[second]:
            second_critical_during_first=True
        length=sum(map(len,queues.values()))
        area+=length
        peak=max(peak,length)
    remaining=sum(map(len,queues.values()))
    if sum(p[0] for p in pair)+total_arrivals!=total_departed+remaining:
        raise AssertionError("vehicle conservation failed")
    return {"queue_area_vehicle_seconds":area,"peak_combined_queue":peak,
        "departed":total_departed,"remaining":remaining,"arrivals":total_arrivals,
        "max_observed_wait_seconds":max_wait,"critical_exposure_vehicle_seconds":critical,
        "overflow_exposure_vehicle_seconds":overflow,
        "second_group_critical_before_service":second_critical_during_first}


def case(family,seed):
    pair=FAMILIES[family]
    # Swap group names on alternating seeds to prevent fixed A ordering bias.
    if seed%2:
        pair=pair[::-1]
    result=evaluate(snapshot(pair))
    if result.operational_decision!="abstain" or result.physical_actuation or result.operationally_validated:
        raise AssertionError("operational safety boundary violated")
    if result.origin!="synthetic_demo":
        raise AssertionError("synthetic origin required")
    major=result.major_group.group_id
    minor=result.minor_group.group_id
    # Match production's integer ticks (tick < floating first window).
    import math
    window=math.ceil(result.minor_first.analysis_first_window_seconds) if result.minor_first else 28
    arrivals,services=exogenous(pair,seed,family=="burst_uncertainty")
    plans={"fixed_a":("A",28),"fixed_b":("B",28),
           "minor_first":(minor,window),"major_first":(major,window)}
    pref=result.preferred_in_simulation
    # Explicit fallback used only in this synthetic comparison, not in the runtime.
    plans["dynamic_x"]=plans[pref] if pref in ("minor_first","major_first") else plans["fixed_a"]
    metrics={k:simulate(pair,arrivals,services,*plan) for k,plan in plans.items()}
    return {"family":family,"seed":seed,"pair":pair,"major":major,"minor":minor,
        "x":result.dynamic_x_safe_vehicles,"minor_feasible":result.minor_clearance_feasible,
        "preference":pref,"reason":result.reason,"fallback_fixed_a":pref not in ("minor_first","major_first"),
        "first_window_ticks":window,"metrics":metrics}


def summarize(rows):
    fields=("queue_area_vehicle_seconds","departed","remaining","peak_combined_queue",
        "max_observed_wait_seconds","critical_exposure_vehicle_seconds","overflow_exposure_vehicle_seconds")
    means={p:{f:fmean(r["metrics"][p][f] for r in rows) for f in fields} for p in POLICIES}
    dynamic_wins=sum(r["metrics"]["dynamic_x"]["queue_area_vehicle_seconds"]<
                     r["metrics"]["major_first"]["queue_area_vehicle_seconds"] for r in rows)
    dynamic_losses=sum(r["metrics"]["dynamic_x"]["queue_area_vehicle_seconds"]>
                       r["metrics"]["major_first"]["queue_area_vehicle_seconds"] for r in rows)
    feasible=[r for r in rows if r["minor_feasible"] and r["preference"]!="no_material_advantage"]
    critical=[r for r in feasible if r["metrics"]["minor_first"]["second_group_critical_before_service"]]
    return {"cases":len(rows),"means":means,"dynamic_queue_area_wins_vs_major":dynamic_wins,
        "dynamic_queue_area_losses_vs_major":dynamic_losses,
        "dynamic_queue_area_ties_vs_major":len(rows)-dynamic_wins-dynamic_losses,
        "minor_feasible_cases":len(feasible),"minor_feasible_critical_before_major_service":len(critical),
        "chosen_minor_cases":sum(r["preference"]=="minor_first" for r in rows),
        "chosen_minor_critical_before_major_service":sum(r["preference"]=="minor_first" and r["metrics"]["dynamic_x"]["second_group_critical_before_service"] for r in rows),
        "preferences":{p:sum(r["preference"]==p for r in rows) for p in ("minor_first","major_first","no_material_advantage","abstain")}}


def run():
    low=evaluate(snapshot(FAMILIES["light_asymmetric"],.64))
    if low.preferred_in_simulation!="abstain" or low.dynamic_x_safe_vehicles is not None:
        raise AssertionError("low confidence must abstain")
    rows=[case(f,s) for f in FAMILIES for s in SEEDS]
    result={"schema_version":1,"scope":"synthetic_counterfactual_not_field",
        "horizon_seconds":HORIZON,"transition_seconds":TRANSITION,"seeds":list(SEEDS),
        "families":{f:summarize([r for r in rows if r["family"]==f]) for f in FAMILIES},
        "overall":summarize(rows),"cases":rows,"low_confidence_abstention_verified":True,
        "x_validated_for_real_traffic":False,"candidate_promoted":False,"commercial_demo_authorized":False,
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
