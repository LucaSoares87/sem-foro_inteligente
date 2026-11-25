import json
import math
import pytest

from src.archive.store import fingerprint
from src.benchmarking.si11_counterfactual import FAMILIES, SEEDS as OLD_SEEDS, snapshot
from src.benchmarking.si11b_robust_x import NOVEL, SEEDS, RISK, RATE_MARGIN, risk_profile, choose, case, run
from src.optimization.engine import evaluate


def test_exact_major_tail_and_net_distribution():
    minor=(1,.1,.8,20)
    major=(4,.2,.7,8)
    row=risk_profile(minor,major)[0]
    # 5 ticks including transition, headroom floor(.85*8)-4=2.
    p=.2+RATE_MARGIN
    expected=sum(math.comb(5,k)*p**k*(1-p)**(5-k) for k in range(3,6))
    assert row["major_critical_probability_assumed"]==pytest.approx(expected)
    assert row["minor_clearance_lower_probability_assumed"]==pytest.approx((1-.15)*.75)
    assert not row["eligible"]


def test_higher_major_demand_cannot_increase_x():
    minor=(2,.1,.8,20)
    lo=risk_profile(minor,(5,.1,.7,30))
    hi=risk_profile(minor,(5,.4,.7,30))
    assert all(a["major_critical_probability_assumed"]<=b["major_critical_probability_assumed"]+1e-12 for a,b in zip(lo,hi))
    assert max(a["x"] for a in lo)>=max(a["x"] for a in hi)
    assert all(0<=r["x"]<=math.floor(.85*minor[3]) for r in lo+hi)


def test_critical_initial_queue_vetoes_every_window():
    profile=risk_profile((1,.1,.9,20),(10,.0,.7,10))
    assert all(r["major_critical_probability_assumed"]==pytest.approx(1.) for r in profile)
    assert all(not r["eligible"] and r["x"]==0 for r in profile)


def test_no_promotion_of_original_nonminor_or_abstention():
    p=FAMILIES["light_asymmetric"]
    low=choose(p,evaluate(snapshot(p,.64)))
    assert low["preference"]=="abstain" and low["window"] is None and low["x"] is None
    for pair in FAMILIES.values():
        original=evaluate(snapshot(pair))
        candidate=choose(pair,original)
        if original.preferred_in_simulation!="minor_first":
            assert candidate["preference"]==original.preferred_in_simulation
        if candidate["preference"]=="minor_first":
            assert candidate["selected"]["major_critical_probability_assumed"]<=RISK+1e-12
            assert candidate["selected"]["minor_clearance_lower_probability_assumed"]>=1-RISK-1e-12


def test_independent_cases_common_workload_and_repeatability():
    assert not set(SEEDS)&set(OLD_SEEDS)
    assert not set(NOVEL)&set(FAMILIES)
    a=case("novel_families","sparse_asymmetric",NOVEL["sparse_asymmetric"],1000)
    assert a==case("novel_families","sparse_asymmetric",NOVEL["sparse_asymmetric"],1000)
    assert len({m["arrivals"] for m in a["metrics"].values()})==1
    for m in a["metrics"].values():
        assert sum(p[0] for p in a["pair"])+m["arrivals"]==m["departed"]+m["remaining"]


def test_full_report_integrity_and_no_promotion():
    d=run()
    assert len(d["cases"])==640 and sum(len(r["metrics"]) for r in d["cases"])==3840
    assert all(c["cases"]==320 for c in d["cohorts"].values())
    assert d["low_confidence_abstention_verified"]
    assert d["candidate_promoted"] is False and d["physical_actuation"] is False
    assert d["x_validated_for_real_traffic"] is False
    assert d["research_gate_passed"]==all(c["all_research_gates_met"] for c in d["cohorts"].values())
    body=json.loads(json.dumps(d))
    digest=body.pop("result_sha256")
    assert digest==fingerprint(body)
