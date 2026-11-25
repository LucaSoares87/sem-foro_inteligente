from collections import deque
import pytest
from src.benchmarking.pimcat_local import (classify,demand_preference,latch_request,scenario,choose,
    streams,simulate,xp_threshold,POLICIES,HORIZON)


def test_empty_is_not_unknown_and_last_is_preserved():
    assert demand_preference(("empty","empty"),1)==(1,"hold_last")
    assert demand_preference(("demand","empty"),1)==(0,"single_demand")
    assert demand_preference(("empty","demand"),0)==(1,"single_demand")
    assert demand_preference(("unknown","empty"),0)==(None,"unknown")
    for kwargs in ({"confidence":.64},{"age_seconds":3},{"available":False},{"occluded":True},
                   {"confidence":float("nan")},{"count":None}):
        args={"count":0,"confidence":.95,"age_seconds":0};args.update(kwargs)
        assert classify(**args)=="unknown"
    assert classify(0,.95,0)=="empty"
    assert classify(1,.95,0)=="demand"


def test_oldest_request_never_reset_by_new_arrival_or_lost_detection():
    assert latch_request(None,10,"unknown",button=True)==10
    assert latch_request(10,40,"demand")==10
    assert latch_request(10,50,"unknown")==10
    assert latch_request(10,60,"empty")==10
    assert latch_request(None,60,"empty") is None


def test_single_ped_deadline_and_compatible_phase():
    q=[deque([0]*20),deque([0]*2)]
    p=deque([(0,0,.9)])
    s=scenario("intense_120")
    phase,reason,_=choose("integrated_xp_no_xv",s,q,p,0,80)
    assert phase=="BP" and reason=="pedestrian_deadline"
    s=scenario("incompatible",limit=90)
    phase,reason,_=choose("integrated_xp_no_xv",s,q,p,0,60)
    assert phase=="P" and reason=="pedestrian_deadline"
    assert xp_threshold(s,q,70)<=xp_threshold(s,q,0)


@pytest.mark.parametrize("policy",POLICIES)
def test_reproducible_and_conservation(policy):
    s=scenario("slow_crossing")
    args=streams("slow_crossing",6000)
    a=simulate(policy,s,*args)
    assert a==simulate(policy,s,*args)
    assert a["vehicle_arrivals"]==a["vehicle_departed"]+a["vehicle_remaining"]
    assert a["pedestrian_arrivals"]==a["pedestrian_completed"]+a["pedestrian_waiting"]+a["pedestrian_crossing"]
    assert a["conflict_violations"]==0
    assert len(a["plans"])==HORIZON//40


def test_no_demand_no_switch_and_emergence():
    for policy in POLICIES[1:]:
        a=simulate(policy,scenario("empty"),*streams("empty",6000))
        assert a["phase_changes"]==0 and a["pedestrian_admitted"]==0
        b=simulate(policy,scenario("emergence_b"),*streams("emergence_b",6000))
        assert b["vehicle_departed"]>0
        assert all(p["phase"]=="B" for p in b["plans"][3:])


def test_unexpected_slow_crossing_blocks_conflicting_service():
    s=scenario("slow_crossing")
    a=[[0,0,0] for _ in range(HORIZON)]
    a[86][2]=1 # fixed P block at 80, admission after transition
    result=simulate("fixed",s,a,[[1,1]]*HORIZON,[.4]*HORIZON)
    assert result["pedestrian_completed"]==1
    assert result["extension_ticks"]>0 and result["protection_blocks"]>0


def test_incompatible_never_uses_carona():
    for policy in POLICIES:
        a=simulate(policy,scenario("incompatible"),*streams("incompatible",6001))
        assert a["compatible_admissions"]==0
        assert all(p["phase"]!="BP" for p in a["plans"])
