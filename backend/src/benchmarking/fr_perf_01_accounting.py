"""FR-PERF-01 research-only accounting; no runner or operational configuration."""
import math
from statistics import median

DURATION = 100
RATE = 5
OFFERED = DURATION * RATE

def trial_order(cpu_budget):
    """Three fixed, balanced rotations; do not adapt order to results."""
    if type(cpu_budget) is not int or cpu_budget < 1:
        raise ValueError("invalid CPU budget")
    configs = [n for n in (1, 2, 4) if n <= cpu_budget]
    return [configs[i % len(configs):] + configs[:i % len(configs)] for i in range(3)]

def finite(x):
    return type(x) in (int, float) and math.isfinite(x) and x >= 0

def distribution(values):
    if not values:
        return None
    if not all(finite(x) for x in values):
        raise ValueError("invalid latency")
    ordered = sorted(values)
    return {"count":len(ordered), "p50":median(ordered),
            "p95":ordered[math.ceil(.95*len(ordered))-1], "max":ordered[-1]}

def summarize_paced(offers, completions, overwritten, discarded, pending):
    """Exact slot IDs 0..499, relative monotonic seconds, including drain.
    Every offer has exactly one terminal disposition. No RTSP timestamp inference.
    Missing offers/lineage/invalid clocks are evidence errors, not zero latency.
    """
    expected = set(range(OFFERED))
    if any(type(k) is not int for k in offers) or set(offers) != expected:
        raise ValueError("missing or invalid offer identity")
    if any(not finite(t) or t < k/RATE for k,t in offers.items()):
        raise ValueError("invalid publication clock")
    groups = [list(completions), list(overwritten), list(discarded), list(pending)]
    ids = [k for group in groups for k in group]
    if any(type(k) is not int for k in ids) or len(ids)!=OFFERED or set(ids)!=expected:
        raise ValueError("nonconserving or duplicate terminal disposition")
    ages=[]; inference=[]; receive=[]; within=0
    for k,event in completions.items():
        done=event["done"]; received=event["received"]; infer=event["inference_ms"]
        if not all(finite(x) for x in (done,received,infer)) or not offers[k]<=received<=done:
            raise ValueError("invalid completion lineage or clock")
        if done>DURATION+15:
            raise ValueError("drain timeout")
        ages.append((done-k/RATE)*1000)
        receive.append((done-received)*1000)
        inference.append(infer)
        within+=int(done<=DURATION)
    age=distribution(ages)
    share=within/OFFERED
    return dict(offered=OFFERED, completed=len(completions), completed_within_window=within,
        overwritten=len(overwritten),discarded=len(discarded),pending=len(pending),
        effective_fps=within/DURATION, completion_share=share,
        offer_to_analytics_ms=age,receive_to_analytics_ms=distribution(receive),
        inference_ms=distribution(inference),
        publication_lag_ms=distribution([(t-k/RATE)*1000 for k,t in offers.items()]),
        capacity_gate=not pending and share>=.95 and age is not None and age["p95"]<=200)

def coverage(times, elapsed):
    """Sample coverage including both boundaries, same D minima."""
    if not finite(elapsed) or elapsed<DURATION or len(times)<95:
        return False
    if not all(finite(t) and t<=elapsed for t in times):
        return False
    return times[0]<=3 and elapsed-times[-1]<=3 and all(0<b-a<=3 for a,b in zip(times,times[1:]))
