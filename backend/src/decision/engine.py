from src.archive.store import fingerprint
from src.decision.contracts import Comparison, CycleResult, SimulationResult

# Abstract simulation units: these are NOT physical timing or safety parameters.
CYCLE=60
IDLE=2
BUDGET=CYCLE-2*IDLE
MIN_SERVICE=12
MAX_SERVICE=BUDGET-MIN_SERVICE
FIXED=BUDGET//2
MAX_CHANGE=6
CAPACITY=2

def allocate(qa,qb,prior,previous):
    """Causal allocation: use the queue at cycle start and prior arrivals only."""
    demand_a=qa+prior[0]
    demand_b=qb+prior[1]
    target=round(BUDGET*demand_a/(demand_a+demand_b)) if demand_a+demand_b else FIXED
    return max(MIN_SERVICE,previous-MAX_CHANGE,min(MAX_SERVICE,previous+MAX_CHANGE,target))

def simulate(scenario,policy):
    if policy not in {"fixed","adaptive"}:
        raise ValueError("unsupported simulation policy")
    qa,qb=scenario.initial_a,scenario.initial_b
    prior=(0,0)
    previous=FIXED
    cycles=[]
    area_a=area_b=0
    for index,demand in enumerate(scenario.cycles,1):
        a=FIXED if policy=="fixed" else allocate(qa,qb,prior,previous)
        b=BUDGET-a
        served_a=served_b=area=0
        peak=qa+qb
        for tick in range(CYCLE):
            # Identical deterministic integer arrivals for both policies.
            qa+=(tick+1)*demand.a//CYCLE-tick*demand.a//CYCLE
            qb+=(tick+1)*demand.b//CYCLE-tick*demand.b//CYCLE
            peak=max(peak,qa+qb)
            # Only one abstract queue may receive service in a tick.
            if tick<a:
                served=min(CAPACITY,qa)
                qa-=served
                served_a+=served
            elif a+IDLE<=tick<a+IDLE+b:
                served=min(CAPACITY,qb)
                qb-=served
                served_b+=served
            # Remaining ticks are deliberately idle.
            area_a+=qa
            area_b+=qb
            area+=qa+qb
        cycles.append(CycleResult(cycle=index,service_a_ticks=a,service_b_ticks=b,
           idle_ticks=2*IDLE,arrivals_a=demand.a,arrivals_b=demand.b,served_a=served_a,
           served_b=served_b,end_a=qa,end_b=qb,queue_area=area,peak_combined=peak))
        prior=(demand.a,demand.b)
        previous=a
    return SimulationResult(policy=policy,cycles=tuple(cycles),
        arrivals=sum(c.arrivals_a+c.arrivals_b for c in cycles),
        initial_queue=scenario.initial_a+scenario.initial_b,
        served=sum(c.served_a+c.served_b for c in cycles),final_queue=qa+qb,
        queue_area=area_a+area_b,peak_combined=max(c.peak_combined for c in cycles),
        queue_area_a=area_a,queue_area_b=area_b)

def compare(scenario):
    fixed=simulate(scenario,"fixed")
    adaptive=simulate(scenario,"adaptive")
    if (adaptive.queue_area,adaptive.final_queue,adaptive.peak_combined,
        adaptive.queue_area_a,adaptive.queue_area_b)==(
        fixed.queue_area,fixed.final_queue,fixed.peak_combined,fixed.queue_area_a,fixed.queue_area_b):
        preferred,reason="equivalent","equal_outcomes"
    elif (adaptive.queue_area<fixed.queue_area and adaptive.final_queue<=fixed.final_queue
          and adaptive.peak_combined<=fixed.peak_combined
          and adaptive.queue_area_a<=fixed.queue_area_a and adaptive.queue_area_b<=fixed.queue_area_b):
        preferred,reason="adaptive","lower_queue_area_without_regression"
    else:
        preferred,reason="fixed","adaptive_tradeoff_or_no_gain"
    payload=scenario.model_dump(mode="json")
    digest=fingerprint({"algorithm":"abstract_two_queue_v1","scenario":payload,
        "fixed":fixed.model_dump(mode="json"),"adaptive":adaptive.model_dump(mode="json")})
    return Comparison(scenario=scenario,scenario_sha256=fingerprint(payload),result_sha256=digest,
        fixed=fixed,adaptive=adaptive,preferred_in_simulation=preferred,reason=reason,
        queue_area_reduction_pct=(100*(fixed.queue_area-adaptive.queue_area)/fixed.queue_area
                                  if fixed.queue_area else None))
