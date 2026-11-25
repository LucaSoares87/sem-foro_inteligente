"""I1A: isolated RP08 advance-only counterfactual research, never runtime."""
import argparse
import json
import math
import tempfile
from pathlib import Path
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking import pimcat_h2_gap as h2

CANDIDATE = "advance_only"
POLICIES = (*h2.POLICIES, CANDIDATE)
SEEDS = tuple(range(11200, 11204))


def choose(policy, kind, phase, age, t, qs, ages, waiting, oldest, rates, clearance, bound):
    args = (kind, phase, age, t, qs, ages, waiting, oldest, rates, clearance, bound)
    if policy != CANDIDATE:
        if policy not in h2.POLICIES:
            raise ValueError("unknown research policy")
        return h2.choose(policy, *args)
    base, reason = h2.choose("compatible", *args)
    # Preserve every service and phase change already recommended by the baseline.
    # The extra condition is a preference only; protection stays in the H2 harness.
    if (base, reason) != ("A", "await_compatible"):
        return base, reason
    if (not waiting or oldest is None or phase != "A" or age < 12 or t % 5
            or t - oldest >= h2.PED_LIMIT - 20 or max(ages) >= h2.VEH_LIMIT - 20):
        return base, reason
    if bound is None or not math.isfinite(bound) or bound < 0:
        return base, reason
    if bound >= 5 + 10 + clearance + 5 + 3:
        return ("BP" if kind == "cross" else "P"), "gap_candidate"
    return base, reason


def paired_differences(rows):
    out = {}
    for baseline in h2.POLICIES:
        out[baseline] = {}
        for key in ("a_stops", "person_area", "pedestrian_area", "pedestrian_max_wait"):
            ds = [r["metrics"][CANDIDATE][key] - r["metrics"][baseline][key] for r in rows]
            out[baseline][key] = {
                "mean_candidate_minus_baseline": fmean(ds),
                "lower": sum(d < 0 for d in ds),
                "equal": sum(d == 0 for d in ds),
                "higher": sum(d > 0 for d in ds),
            }
    return out


def assess(rows):
    groups = {
        "overall": rows,
        "mid": [r for r in rows if r["topology"] == "mid"],
        "cross": [r for r in rows if r["topology"] == "cross"],
        "stress": [r for r in rows if r["family"] in ("mid_slow", "cross_deadlines")],
    }
    summaries = {k: h2.summarize(v, POLICIES) for k, v in groups.items()}
    families = {f: h2.summarize([r for r in rows if r["family"] == f], POLICIES)
                for f in h2.FAMILIES}
    g = {k: h2.gate(summaries[k], CANDIDATE) for k in ("mid", "cross", "stress")}
    overall = summaries["overall"]
    choices = sum(r["metrics"][CANDIDATE]["gap_choices"] for r in rows)
    g["directional_stop_reduction"] = overall[CANDIDATE]["a_stops"] < overall["compatible"]["a_stops"]
    g["incremental_opportunity_observed"] = choices > 0
    g["passed"] = all(g[k]["passed"] for k in ("mid", "cross", "stress")) and g["directional_stop_reduction"] and g["incremental_opportunity_observed"]
    return summaries, families, g, choices


def run():
    api = h2.ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-i1a-") as d:
        rows = [h2.case(api, Path(d) / f"{f}-{s}", f, s, POLICIES, choose_fn=choose)
                for f in h2.FAMILIES for s in SEEDS]
    summaries, families, g, choices = assess(rows)
    report = {
        "scope": "pimcat_i1a_advance_only_synthetic_not_field",
        "sumo_version": h2.VERSION,
        "cases": len(rows), "trajectories": len(rows) * len(POLICIES),
        "horizon_seconds": h2.HORIZON, "seeds": list(SEEDS), "policies": list(POLICIES),
        "summaries": summaries, "families": families, "paired_differences": paired_differences(rows),
        "incremental_gap_choices": choices, "gates": {CANDIDATE: g}, "rows": rows,
        "research_gate_passed": g["passed"],
        "c3_independent_precision": "BLOCKED_BY_INDEPENDENT_ANNOTATION",
        "real_gap_calibration": "NOT_RUN", "candidate_promoted": False,
        "physical_actuation": False, "operationally_validated": False,
        "commercial_demo_authorized": False, "operational_decision": "abstain",
    }
    report["result_sha256"] = fingerprint(report)
    return report


def verify(report):
    d = dict(report)
    sha = d.pop("result_sha256")
    assert fingerprint(d) == sha
    assert d["scope"] == "pimcat_i1a_advance_only_synthetic_not_field"
    assert d["cases"] == 24 and d["trajectories"] == 120
    assert d["seeds"] == list(SEEDS) and d["policies"] == list(POLICIES)
    assert d["horizon_seconds"] == h2.HORIZON and d["sumo_version"] == h2.VERSION
    assert d["c3_independent_precision"] == "BLOCKED_BY_INDEPENDENT_ANNOTATION"
    assert d["real_gap_calibration"] == "NOT_RUN" and d["operational_decision"] == "abstain"
    assert all(d[k] is False for k in ("candidate_promoted", "physical_actuation",
                                      "operationally_validated", "commercial_demo_authorized"))
    rows = d["rows"]
    assert len(rows) == d["cases"]
    assert {(r["family"], r["seed"]) for r in rows} == {(f, s) for f in h2.FAMILIES for s in SEEDS}
    for r in rows:
        assert r["conflicts_verified"] and r["topology"] == h2.FAMILIES[r["family"]][0]
        assert set(r["metrics"]) == set(POLICIES)
        for p, m in r["metrics"].items():
            assert m["runtime_version"].split()[-1] == h2.VERSION
            assert m["vehicles_scheduled"] == m["vehicles_exited"] + m["vehicles_remaining"] + m["vehicles_uninserted"]
            assert m["pedestrians_scheduled"] == m["pedestrians_exited"] + m["pedestrians_remaining"] + m["pedestrians_uninserted"]
            assert m["pedestrians_admitted"] == m["pedestrians_completed"] + m["pedestrians_crossing"]
            assert m["pedestrians_requested"] == m["pedestrians_admitted"] + m["pedestrians_waiting"]
            assert not any(m[k] for k in ("red_entries", "conflict_violations", "colliding_vehicle_events", "overspeed_samples", "teleports"))
            assert m["protected_episodes_zero_new_A_stops"] <= m["protected_episodes_complete"]
            if p == CANDIDATE:
                assert m["gap_deferred"] == 0
    summaries, families, gate, choices = assess(rows)
    assert d["summaries"] == summaries and d["families"] == families
    assert d["gates"] == {CANDIDATE: gate} and d["research_gate_passed"] == gate["passed"]
    assert d["incremental_gap_choices"] == choices
    assert d["paired_differences"] == paired_differences(rows)
    return gate


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    report = run()
    # Preserve raw result before the accounting verifier, including negative scientific gates.
    with Path(args.output).open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps(verify(report), sort_keys=True))


if __name__ == "__main__":
    main()
