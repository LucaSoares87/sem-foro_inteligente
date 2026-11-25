"""I1B offline ETA calibration on independent training seeds and held-out SUMO corridors."""
import argparse
import json
import math
import tempfile
from pathlib import Path
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking import pimcat_d_sumo as d

TRAIN = (12300, 12301)
TEST = tuple(range(12400, 12404))
CANDIDATES = {"calibrated_eta": "adaptive_eta",
              "calibrated_eta_storage": "adaptive_eta_storage"}
POLICIES = (*d.POLICIES, *CANDIDATES)
MIN_SUPPORT = 30


def distance_class(distance):
    return "short" if distance <= 150 else "long"


def keys(distance, queued):
    k = distance_class(distance)
    return (k + ("_queued" if queued else "_clear"), k, "global")


def quantile(values, q):
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)]


def fit(training):
    groups = {}
    for r in training:
        assert r["seed"] in TRAIN
        for distance, queued, duration, lo, nominal, hi in r["metrics"]["independent"]["eta_samples"]:
            for key in keys(distance, queued):
                g = groups.setdefault(key, {"issued": 0, "arrived": []})
                g["issued"] += 1
                if duration is not None:
                    g["arrived"].append(duration)
    result = {}
    for key, g in groups.items():
        v = g["arrived"]
        result[key] = {"issued": g["issued"], "arrived": len(v),
                       "censored": g["issued"]-len(v),
                       "quantiles": [quantile(v, q) for q in (.1, .5, .9)] if len(v) >= MIN_SUPPORT else None}
    return result


def predictor(model):
    def estimate(t, count, distance, queued):
        original = d.forecast(t, count, distance)
        if type(queued) is not int or queued < 0:
            raise ValueError("invalid queue observation")
        for key in keys(distance, queued):
            entry = model.get(key)
            if entry and entry["arrived"] >= MIN_SUPPORT and entry["quantiles"] is not None:
                lo, med, hi = entry["quantiles"]
                lower = max(0, math.ceil(distance / d.VMAX) - 1, lo)
                med = max(lower, med)
                hi = max(med, hi)
                return d.Cohort(t, count, t+lower, t+med, t+hi, t+hi+5)
        return original
    return estimate


def evaluate_case(api, root, family, seed, estimate):
    # One common route file per case; reconstructing it for the candidates must hash identically.
    row = d.case(api, root, family, seed, d.POLICIES, collect_eta=True)
    alternative = d.case(api, root, family, seed, tuple(CANDIDATES.values()),
                         forecast_fn=estimate, collect_eta=True)
    assert all(row[k] == alternative[k] for k in ("network_sha256", "demand_sha256", "nodes", "family", "seed"))
    for k, p in CANDIDATES.items():
        row["metrics"][k] = alternative["metrics"][p]
    return row


def eta_details(rows, policy):
    samples = [s for r in rows for s in r["metrics"][policy]["eta_samples"]]
    arrived = [s for s in samples if s[2] is not None]
    return {"issued": len(samples), "arrived": len(arrived), "censored": len(samples)-len(arrived),
            "censored_share": 1-len(arrived)/len(samples) if samples else None,
            "mean_interval_width": fmean(s[5]-s[3] for s in samples) if samples else None,
            "early_arrivals": sum(s[2]<s[3] for s in arrived),
            "late_arrivals": sum(s[2]>s[5] for s in arrived)}


def paired(rows, candidate, baseline):
    out = {}
    for key in ("person_area", "pedestrian_max_wait", "mean_corridor_stops",
                "corridor_speed_cv", "mean_corridor_travel_seconds", "eta_coverage", "eta_mae_seconds"):
        diffs = []
        for r in rows:
            a, b = r["metrics"][candidate][key], r["metrics"][baseline][key]
            if a is not None and b is not None:
                diffs.append(a-b)
        out[key] = {"comparable": len(diffs), "lower": sum(x<0 for x in diffs),
                    "equal": sum(x==0 for x in diffs), "higher": sum(x>0 for x in diffs),
                    "mean_delta": fmean(diffs) if diffs else None}
    return out


def assess(rows):
    groups = {"overall": rows, "two": [r for r in rows if r["nodes"]==2],
              "three": [r for r in rows if r["nodes"]==3],
              "stress": [r for r in rows if r["family"] in ("two_compact","three_storage")]}
    summaries = {k: d.summary(v, POLICIES) for k,v in groups.items()}
    eta = {k: {p: eta_details(v,p) for p in POLICIES} for k,v in groups.items()}
    gates = {}
    def le(a,b,extra=0):
        return a is not None and b is not None and a<=b+extra
    for p,baseline in CANDIDATES.items():
        g = {}
        for k in ("two","three","stress"):
            s = summaries[k]
            a,b = eta[k][p],eta[k][baseline]
            original = d.gate(s,p)
            extra = {"coverage_not_lower": le(s[baseline]["eta_coverage"], s[p]["eta_coverage"]),
                     "mae_not_higher": le(s[p]["eta_mae_seconds"],s[baseline]["eta_mae_seconds"]),
                     "width_bounded": le(a["mean_interval_width"],b["mean_interval_width"],30),
                     "censor_bounded": le(a["censored_share"],b["censored_share"],.05)}
            g[k] = {"original_D_gate": original, "additional": extra,
                    "passed": original["passed"] and all(extra.values())}
        g["improvement_vs_independent"] = summaries["overall"][p]["person_area"] < summaries["overall"]["independent"]["person_area"]
        g["passed"] = g["improvement_vs_independent"] and all(g[k]["passed"] for k in ("two","three","stress"))
        gates[p]=g
    return summaries,eta,gates


def verify_case(row, policies):
    assert row["conflicts_verified"] and set(row["metrics"])==set(policies)
    for m in row["metrics"].values():
        assert m["runtime_version"].split()[-1]==d.VERSION
        assert m["vehicle_scheduled"]==m["vehicle_exited"]+m["vehicle_remaining"]+m["vehicle_uninserted"]
        assert m["pedestrian_scheduled"]==m["pedestrian_exited"]+m["pedestrian_remaining"]+m["pedestrian_uninserted"]
        assert m["pedestrian_admitted"]==m["pedestrian_completed"]+m["pedestrian_crossing"]
        assert m["eta_issued"]==m["eta_arrived"]+m["eta_censored"]
        assert m["vehicle_area"]==m["corridor_vehicle_area"]+m["transverse_vehicle_area"]
        assert math.isclose(m["critical_exposure"],sum(m["segment_critical_exposure"]))
        assert not any(m[k] for k in ("mid_empty_interruptions","collisions","teleports","overspeed_samples","conflict_violations","red_entries"))
        samples=m["eta_samples"]
        assert len(samples)==m["eta_issued"]
        assert all(s[0]>0 and s[1]>=0 and 0<=s[3]<=s[4]<=s[5] and (s[2] is None or s[2]>=0) for s in samples)
        arrived=[s for s in samples if s[2] is not None]
        assert len(arrived)==m["eta_arrived"]
        assert sum(s[3]<=s[2]<=s[5] for s in arrived)==m["eta_covered"]
        assert sum(abs(s[2]-s[4]) for s in arrived)==m["eta_abs_error_sum"]


def run():
    api=d.ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-i1b-") as folder:
        root=Path(folder)
        training=[d.case(api,root/f"train-{f}-{s}",f,s,("independent",),collect_eta=True)
                  for f in d.FAMILIES for s in TRAIN]
        for r in training: verify_case(r,("independent",))
        model=fit(training)
        estimate=predictor(model)
        rows=[evaluate_case(api,root/f"test-{f}-{s}",f,s,estimate) for f in d.FAMILIES for s in TEST]
    summaries,eta,gates=assess(rows)
    report={"scope":"pimcat_i1b_eta_synthetic_not_field","sumo_version":d.VERSION,
            "training_seeds":list(TRAIN),"test_seeds":list(TEST),"training_trajectories":len(training),
            "cases":len(rows),"test_trajectories":len(rows)*len(POLICIES),"policies":list(POLICIES),
            "model":model,"training":training,"rows":rows,"summaries":summaries,"eta_details":eta,"gates":gates,
            "paired":{p:paired(rows,p,b) for p,b in CANDIDATES.items()},
            "research_gate_passed":any(g["passed"] for g in gates.values()),
            "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","field_speed_calibration":"NOT_RUN",
            "candidate_promoted":False,"operationally_validated":False,"physical_actuation":False,
            "commercial_demo_authorized":False,"operational_decision":"abstain"}
    report["result_sha256"]=fingerprint(report)
    return report


def verify(report):
    r=dict(report); sha=r.pop("result_sha256")
    assert fingerprint(r)==sha
    assert r["scope"]=="pimcat_i1b_eta_synthetic_not_field" and r["sumo_version"]==d.VERSION
    assert r["training_seeds"]==list(TRAIN) and r["test_seeds"]==list(TEST) and not set(TRAIN)&set(TEST)
    assert r["training_trajectories"]==16 and r["cases"]==32 and r["test_trajectories"]==192
    assert r["policies"]==list(POLICIES)
    for rows,seeds,policies in ((r["training"],TRAIN,("independent",)),(r["rows"],TEST,POLICIES)):
        assert len(rows)==len(d.FAMILIES)*len(seeds)
        assert {(x["family"],x["seed"]) for x in rows}=={(f,s) for f in d.FAMILIES for s in seeds}
        for x in rows:verify_case(x,policies)
    assert r["model"]==fit(r["training"])
    s,e,g=assess(r["rows"])
    assert r["summaries"]==s and r["eta_details"]==e and r["gates"]==g
    assert r["paired"]=={p:paired(r["rows"],p,b) for p,b in CANDIDATES.items()}
    assert r["research_gate_passed"]==any(x["passed"] for x in g.values())
    assert r["c3_independent_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"
    assert r["field_speed_calibration"]=="NOT_RUN" and r["operational_decision"]=="abstain"
    assert all(r[k] is False for k in ("candidate_promoted","operationally_validated","physical_actuation","commercial_demo_authorized"))
    return g


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    report=run()
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps(verify(report),sort_keys=True))
    print(json.dumps(report["paired"],sort_keys=True))


if __name__=="__main__":
    main()
