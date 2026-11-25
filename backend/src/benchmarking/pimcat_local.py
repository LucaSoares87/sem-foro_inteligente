"""PIMCAT B/C1: offline abstract multimodal FIFO research; no runtime integration."""
import argparse
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from random import Random
from statistics import fmean

from src.benchmarking.si11c_predictive_x import observed
from src.optimization.engine import evaluate

BLOCK=40
HORIZON=480
TRANSITION=4
ENTRY=7
PED_LIMIT=120
VEH_LIMIT=180
CAPACITY=40
SEEDS=tuple(range(6000,6008))
POLICIES=("fixed","actuated","grouped","compatible","proportional",
          "integrated_xp_no_xv","integrated_xp")
# rates A/B/P, length metres, compatibility B, unexpected slow person speed
FAMILIES={
 "empty":(0,0,0,8,True,False),
 "single_a":(.22,0,0,8,True,False),
 "emergence_b":(0,.20,0,8,True,False),
 "balanced":(.20,.20,0,12,True,False),
 "asymmetric_a":(.45,.08,.03,12,True,False),
 "isolated_ped":(.04,.02,0,12,True,False),
 "group_ped":(.25,.20,.22,12,True,False),
 "intense_120":(.45,.30,.10,16,True,False),
 "compatible":(.08,.38,.12,12,True,False),
 "incompatible":(.35,.30,.12,12,False,False),
 "slow_crossing":(.24,.25,.14,16,True,True),
 "simultaneous_deadlines":(.55,.55,.28,16,False,False),
}
BASE=tuple(FAMILIES)[:6]
STRESS=tuple(FAMILIES)[6:]


def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def classify(count,confidence,age_seconds,available=True,occluded=False):
    """Unknown is not empty. Thresholds for research unit tests, not field calibration."""
    if (not available or occluded or type(count) is not int or count<0 or
        not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or
        not .65<=confidence<=1 or not isinstance(age_seconds,(int,float)) or
        not math.isfinite(age_seconds) or not 0<=age_seconds<=2):
        return "unknown"
    return "demand" if count else "empty"


def demand_preference(states,last):
    if last not in (0,1) or len(states)!=2 or any(s not in ("empty","demand") for s in states):
        return None,"unknown"
    if states==("empty","empty"):return last,"hold_last"
    if states==("demand","empty"):return 0,"single_demand"
    if states==("empty","demand"):return 1,"single_demand"
    return None,"compare_both"


def latch_request(oldest,now,observation,button=False):
    """Preserve outstanding oldest request; clearing requires separate admission evidence."""
    if oldest is not None:return oldest
    return now if button or observation=="demand" else None


@dataclass(frozen=True)
class Scenario:
    rates: tuple
    length: int
    compatible_b: bool
    unexpected_slow: bool
    pedestrian_limit: int=PED_LIMIT

    def __post_init__(self):
        if not 1<=self.pedestrian_limit<=600 or self.clearance+ENTRY+TRANSITION+1>BLOCK:
            raise ValueError("invalid abstract experiment settings")

    @property
    def clearance(self):return math.ceil(1+self.length/.6)

    @property
    def protected(self):return ENTRY+self.clearance+1


def scenario(name,limit=PED_LIMIT):
    a,b,p,l,compat,slow=FAMILIES[name]
    return Scenario((a,b,p),l,compat,slow,limit)


def streams(name,seed):
    s=scenario(name)
    rng=Random(seed)
    arrivals=[];services=[];speeds=[]
    for t in range(HORIZON):
        rates=list(s.rates)
        if name=="emergence_b" and t<80:rates[1]=0
        if name=="group_ped":rates[2]*=1.8 if t%80<40 else .2
        row=[int(rng.random()<min(1,r)) for r in rates]
        if name=="isolated_ped":row[2]=int(t==41)
        arrivals.append(row)
        services.append([int(rng.random()<.8),int(rng.random()<.8)])
        # Unexpected slow walker occurs in a pre-generated subset, unknown to policy.
        speeds.append(.4 if s.unexpected_slow and rng.random()<.25 else .9)
    return arrivals,services,speeds


def proportional(q,rates,last):
    scores=[len(q[g])+BLOCK*rates[g] for g in (0,1)]
    return last if scores[0]==scores[1] else int(scores[1]>scores[0])


def local_vehicle(q,s,last,t,use_x):
    states=tuple("demand" if x else "empty" for x in q)
    selected,reason=demand_preference(states,last)
    if reason!="compare_both":return selected,reason
    selected=proportional(q,s.rates,last)
    if not use_x:return selected,"proportional"
    if max(map(len,q))>200:return selected,"x_contract_abstention"
    pair=tuple((0,s.rates[g],.8,CAPACITY) for g in (0,1))
    result=evaluate(observed(pair,q,t))
    assert result.operational_decision=="abstain" and not result.physical_actuation
    pref=result.preferred_in_simulation
    if pref in ("minor_first","major_first"):
        group=result.minor_group if pref=="minor_first" else result.major_group
        return int(group.group_id=="B"),"original_x_"+pref
    return selected,"x_"+pref+"_proportional"


def xp_threshold(s,q,p_age):
    groups=(0,) if s.compatible_b else (0,1)
    d=s.protected
    delta=BLOCK
    cost=1.5*d*sum(len(q[g])+s.rates[g]*d/2 for g in groups)
    return max(1,math.ceil(cost/(delta*(1+p_age/s.pedestrian_limit))-s.rates[2]*delta/2))


def choose(policy,s,q,p,last,t):
    """Return an abstract block label and audit reason; only synthetic data."""
    if policy not in POLICIES:raise ValueError("unknown policy")
    if policy=="fixed":return ("A","B","P")[t//BLOCK%3],"fixed",None
    base,reason=local_vehicle(q,s,last,t,policy=="integrated_xp")
    assert base in (0,1)
    ages=[t-queue[0] if queue else -1 for queue in q]
    age=t-p[0][1] if p else -1
    # Compare due dates, not group size. The last available entry tick is included.
    v_urgent=[g for g in (0,1) if ages[g]>=VEH_LIMIT-BLOCK-TRANSITION]
    p_urgent=bool(p) and age+BLOCK+TRANSITION+ENTRY-1>=s.pedestrian_limit
    carona=policy in ("compatible","proportional","integrated_xp","integrated_xp_no_xv") and s.compatible_b
    if v_urgent:
        base=min(v_urgent,key=lambda g:(VEH_LIMIT-ages[g],g!=last,g))
        reason="vehicle_deadline"
    phase=("A","B")[base]
    if not p:return phase,reason,None
    if carona and base==1:return "BP","compatible",None
    if p_urgent:
        if v_urgent and VEH_LIMIT-ages[base]<s.pedestrian_limit-age:
            return phase,"competing_vehicle_deadline",None
        return "BP" if carona else "P","pedestrian_deadline",None
    if v_urgent:return phase,reason,None
    if policy=="actuated":return "P","request",None
    if policy=="grouped":
        return ("P","group",None) if len(p)>=4 else (phase,reason,None)
    if not q[0] and (s.compatible_b or not q[1]):
        return ("BP" if carona else "P"),"conflicting_demand_empty",None
    if policy=="compatible":return phase,reason,None
    if policy=="proportional":
        return (("BP" if carona else "P"),"person_demand",None) if len(p)>=1.5*len(q[base]) else (phase,reason,None)
    threshold=xp_threshold(s,q,age)
    return (("BP" if carona else "P"),"xp_threshold",threshold) if len(p)>=threshold else (phase,reason,threshold)


def conflicts(group,compatible_b):
    return group==0 or not compatible_b


def simulate(policy,s,arrivals,services,speeds):
    q=[deque(),deque()];p=deque();crossing=[]
    last=0;previous="A";phase="A";transition=0;entry_end=0
    planned_until=-1;actual_until=-1
    v_arr=v_out=p_arr=p_done=p_admit=0
    v_area=p_area=critical=0.
    v_wait=[];p_wait=[];v_late=set();p_late=set()
    changes=empty_green=empty_p=compatible_count=extensions=protection_blocks=0
    plans=[];p_on_time=0
    for t in range(HORIZON):
        for g in (0,1):
            if arrivals[t][g]:q[g].append(t);v_arr+=1
        if arrivals[t][2]:
            p.append((p_arr,t,speeds[t]));p_arr+=1
        completed=[row for row in crossing if row[1]<=t]
        p_done+=len(completed)
        crossing=[row for row in crossing if row[1]>t]
        if t%BLOCK==0:
            phase,reason,xp=choose(policy,s,q,p,last,t)
            assert phase in ("A","B","P","BP") and (phase!="BP" or s.compatible_b)
            transition=TRANSITION if phase!=previous else 0
            changes+=int(phase!=previous)
            previous=phase
            entry_end=t+transition+ENTRY
            if phase in ("P","BP"):
                empty_p+=int(not p)
                planned_until=max(planned_until,entry_end+s.clearance+1)
                assert planned_until<=t+BLOCK
            if phase in ("A","B","BP"):last=int(phase!="A")
            plans.append({"tick":t,"phase":phase,"reason":reason,"xp":xp,
                          "oldest_pedestrian_wait":t-p[0][1] if p else None})
        offset=t%BLOCK
        admitted_now=0
        if phase in ("P","BP") and offset>=transition and t<entry_end:
            for _ in range(min(2,len(p))):
                pid,birth,speed=p.popleft()
                wait=t-birth;p_wait.append(wait)
                p_on_time+=int(wait<=s.pedestrian_limit)
                if wait>s.pedestrian_limit:p_late.add(pid)
                finish=t+math.ceil(1+s.length/speed)
                crossing.append((pid,finish))
                actual_until=max(actual_until,finish+1)
                p_admit+=1;admitted_now+=1
                compatible_count+=int(phase=="BP")
        active=None
        if offset>=transition and phase in ("A","B","BP"):
            active=int(phase!="A")
        if actual_until>planned_until and planned_until<=t<actual_until:extensions+=1
        protected=t<max(planned_until,actual_until) or bool(crossing)
        if active is not None and conflicts(active,s.compatible_b) and protected:
            protection_blocks+=1
            active=None
        # Independent assertions over service and actual occupancy, not merely phase label.
        assert not (active is not None and conflicts(active,s.compatible_b) and
                    (crossing or admitted_now or t<max(planned_until,actual_until)))
        if active is not None:
            if not q[active]:empty_green+=1
            elif services[t][active]:
                birth=q[active].popleft();wait=t-birth;v_wait.append(wait);v_out+=1
                if wait>VEH_LIMIT:v_late.add((active,birth))
        for g in (0,1):
            for birth in q[g]:
                if t+1-birth>VEH_LIMIT:v_late.add((g,birth))
        for pid,birth,_ in p:
            if t+1-birth>s.pedestrian_limit:p_late.add(pid)
        v_area+=sum(map(len,q));p_area+=len(p)
        critical+=sum(max(0,len(row)-.85*CAPACITY) for row in q)
        assert v_arr==v_out+sum(map(len,q))
        assert p_arr==p_done+len(p)+len(crossing)
        assert p_admit==p_done+len(crossing)
    # Completion exactly at the boundary is a completed traversal, not a dropped person.
    p_done+=sum(finish<=HORIZON for _,finish in crossing)
    crossing=[row for row in crossing if row[1]>HORIZON]
    assert p_arr==p_done+len(p)+len(crossing)
    vmax=max(v_wait+[HORIZON-b for row in q for b in row],default=0)
    pmax=max(p_wait+[HORIZON-b for _,b,_ in p],default=0)
    percentile=lambda seq:sorted(seq)[math.ceil(.95*len(seq))-1] if seq else None
    return {"vehicle_arrivals":v_arr,"vehicle_departed":v_out,"vehicle_remaining":sum(map(len,q)),
      "vehicle_area":v_area,"pedestrian_arrivals":p_arr,"pedestrian_admitted":p_admit,
      "pedestrian_completed":p_done,"pedestrian_waiting":len(p),"pedestrian_crossing":len(crossing),
      "pedestrian_area":p_area,"person_area":1.5*v_area+p_area,
      "vehicle_max_wait":vmax,"pedestrian_max_wait":pmax,
      "vehicle_p95_departed":percentile(v_wait),"pedestrian_p95_admitted":percentile(p_wait),
      "vehicle_deadline_violations":len(v_late),"pedestrian_deadline_violations":len(p_late),
      "pedestrian_on_time_admitted":p_on_time,"critical_exposure":critical,"phase_changes":changes,
      "empty_vehicle_ticks":empty_green,"empty_pedestrian_blocks":empty_p,
      "compatible_admissions":compatible_count,"extension_ticks":extensions,"protection_blocks":protection_blocks,
      "conflict_violations":0,"plans":plans}


FIELDS=("vehicle_area","pedestrian_area","person_area","critical_exposure","vehicle_departed",
        "pedestrian_completed","pedestrian_admitted","pedestrian_arrivals","pedestrian_waiting",
        "pedestrian_crossing","vehicle_remaining","vehicle_max_wait","pedestrian_max_wait",
        "vehicle_deadline_violations","pedestrian_deadline_violations","pedestrian_on_time_admitted",
        "phase_changes","empty_vehicle_ticks","empty_pedestrian_blocks","compatible_admissions",
        "extension_ticks","protection_blocks","conflict_violations")


def summarize(rows):
    out={}
    for policy in POLICIES:
        ms=[r["metrics"][policy] for r in rows]
        d={key:fmean(m[key] for m in ms) for key in FIELDS}
        for key in ("vehicle_max_wait","pedestrian_max_wait"):d["worst_"+key]=max(m[key] for m in ms)
        for key in ("vehicle_deadline_violations","pedestrian_deadline_violations","conflict_violations"):
            d["total_"+key]=sum(m[key] for m in ms)
        for key in ("vehicle_p95_departed","pedestrian_p95_admitted"):
            values=[m[key] for m in ms if m[key] is not None]
            d["mean_case_"+key]=fmean(values) if values else None
            d["cases_with_"+key]=len(values)
        admitted=sum(m["pedestrian_admitted"] for m in ms)
        d["on_time_share_admitted"]=sum(m["pedestrian_on_time_admitted"] for m in ms)/admitted if admitted else None
        d["compatible_share_admitted"]=sum(m["compatible_admissions"] for m in ms)/admitted if admitted else None
        d["occupancy_sensitivity"]={str(o):o*d["vehicle_area"]+d["pedestrian_area"] for o in (1,1.5,2)}
        out[policy]=d
    return out


def gate(summary,cohort,candidate):
    c=summary[candidate]
    checks={}
    for baseline in ("compatible","proportional"):
        b=summary[baseline]
        checks[baseline]={**{k:c[k]<=1.05*b[k] for k in ("person_area","pedestrian_area","vehicle_area",
             "critical_exposure","worst_pedestrian_max_wait","worst_vehicle_max_wait")},
            **{k:c[k]>=.95*b[k] for k in ("vehicle_departed","pedestrian_completed")},
            **{k:c[k]<=b[k] for k in ("total_pedestrian_deadline_violations","total_vehicle_deadline_violations")}}
    checks["constraints"]={"no_conflict":c["total_conflict_violations"]==0,
        "base_deadline":cohort!="base" or c["total_pedestrian_deadline_violations"]==0}
    return {"passed":all(x for section in checks.values() for x in section.values()),"checks":checks}


def run():
    rows=[]
    for name in FAMILIES:
        s=scenario(name)
        for seed in SEEDS:
            a,v,p=streams(name,seed)
            rows.append({"family":name,"cohort":"base" if name in BASE else "stress","seed":seed,
               "stream_sha256":digest([a,v,p]),"metrics":{k:simulate(k,s,a,v,p) for k in POLICIES}})
    summaries={"overall":summarize(rows)}
    for cohort in ("base","stress"):
        summaries[cohort]=summarize([r for r in rows if r["cohort"]==cohort])
    gates={}
    for cand in ("integrated_xp","integrated_xp_no_xv"):
        g={c:gate(summaries[c],c,cand) for c in ("base","stress")}
        g["directional_improvement_vs_fixed"]=summaries["overall"][cand]["person_area"]<summaries["overall"]["fixed"]["person_area"]
        g["passed"]=g["directional_improvement_vs_fixed"] and g["base"]["passed"] and g["stress"]["passed"]
        gates[cand]=g
    result={"schema_version":1,"scope":"pimcat_local_abstract_fifo_synthetic",
       "cases":len(rows),"trajectories":len(rows)*len(POLICIES),"horizon_seconds":HORIZON,
       "pedestrian_limit_experimental_seconds":PED_LIMIT,"vehicle_limit_experimental_seconds":VEH_LIMIT,
       "policies":list(POLICIES),"summaries":summaries,"gates":gates,
       "xp_xv_ablation_phase_differences":sum(
          [p["phase"] for p in r["metrics"]["integrated_xp"]["plans"]]!=
          [p["phase"] for p in r["metrics"]["integrated_xp_no_xv"]["plans"]] for r in rows),
       "xp_xv_ablation_audit_differences":sum(
          r["metrics"]["integrated_xp"]["plans"]!=r["metrics"]["integrated_xp_no_xv"]["plans"] for r in rows),
       "research_gate_passed":gates["integrated_xp"]["passed"],"candidate_promoted":False,
       "physical_actuation":False,"operationally_validated":False,"operational_decision":"abstain",
       "perception_validation":"NOT_RUN","sumo_pedestrian_validation":"NOT_RUN","network_validation":"NOT_RUN",
       "rows":rows}
    result["result_sha256"]=digest(result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    result=run()
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True))


if __name__=="__main__":main()
