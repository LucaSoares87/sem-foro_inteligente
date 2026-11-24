from math import floor
from src.archive.store import fingerprint
from src.optimization.contracts import CandidateMetrics,OptimizationResult,ServiceGroupState

HORIZON_SECONDS=60
TRANSITION_OVERHEAD_SECONDS=4
MAX_FIRST_WINDOW_SECONDS=30
CRITICAL_STORAGE_RATIO=.85
MINIMUM_CONFIDENCE=.65
MATERIAL_GAIN_RATIO=.05

# Engineering defaults for comparative simulation only. They are not traffic-controller parameters.
QUEUE_AREA_WEIGHT=1.0
MAX_WAIT_WEIGHT=2.0
SPILLBACK_WEIGHT=25.0
FLOW_INTERRUPTION_WEIGHT=10.0
TRANSITION_WEIGHT=5.0

def aggregate_groups(snapshot):
    grouped={}
    for approach in snapshot.approaches:
        row=grouped.setdefault(approach.service_group,{
            "queue":0,"arrival":0.0,"discharge":0.0,"weighted_wait":0.0,
            "weight":0,"max_wait":0.0,"capacity":0,"confidence":1.0
        })
        row["queue"]+=approach.queue_length
        row["arrival"]+=approach.arrival_rate_vps
        row["discharge"]+=approach.discharge_rate_vps
        weight=max(1,approach.queue_length)
        row["weighted_wait"]+=approach.mean_wait_seconds*weight
        row["weight"]+=weight
        row["max_wait"]=max(row["max_wait"],approach.max_wait_seconds)
        row["capacity"]+=approach.storage_capacity_vehicles
        row["confidence"]=min(row["confidence"],approach.observation_confidence)
    result=[]
    for group_id,row in sorted(grouped.items()):
        result.append(ServiceGroupState(
            group_id=group_id,queue_length=row["queue"],arrival_rate_vps=row["arrival"],
            discharge_rate_vps=row["discharge"],
            mean_wait_seconds=row["weighted_wait"]/row["weight"],
            max_wait_seconds=row["max_wait"],storage_capacity_vehicles=row["capacity"],
            storage_occupancy_ratio=min(2.0,row["queue"]/row["capacity"]),
            observation_confidence=row["confidence"]))
    return tuple(result)

def _major_minor(groups):
    ordered=sorted(groups,key=lambda g:(g.queue_length,g.storage_occupancy_ratio,
                                        g.arrival_rate_vps,g.max_wait_seconds,g.group_id))
    return ordered[-1],ordered[0]

def dynamic_x_safe(minor,major):
    net_clearance=minor.discharge_rate_vps-minor.arrival_rate_vps
    if net_clearance<=0:
        return 0,None
    critical_major=CRITICAL_STORAGE_RATIO*major.storage_capacity_vehicles
    available=max(0.0,critical_major-major.queue_length)
    time_budget=(HORIZON_SECONDS-TRANSITION_OVERHEAD_SECONDS if major.arrival_rate_vps<=1e-9
                 else available/major.arrival_rate_vps-TRANSITION_OVERHEAD_SECONDS)
    safe=max(0,floor(net_clearance*max(0.0,time_budget)))
    safe=min(safe,floor(CRITICAL_STORAGE_RATIO*minor.storage_capacity_vehicles))
    return safe,minor.queue_length/net_clearance

def _simulate(minor,major,minor_first,first_window):
    q={"minor":float(minor.queue_length),"major":float(major.queue_length)}
    groups={"minor":minor,"major":major}
    area=spill=flow_interrupt=0.0
    peak=sum(q.values())
    unserved={"minor":0,"major":0}
    for tick in range(HORIZON_SECONDS):
        if tick<first_window:
            active="minor" if minor_first else "major"
        elif tick<first_window+TRANSITION_OVERHEAD_SECONDS:
            active=None
        else:
            active="major" if minor_first else "minor"
        for key in ("minor","major"):
            group=groups[key]
            q[key]+=group.arrival_rate_vps
            if active==key:
                q[key]=max(0.0,q[key]-group.discharge_rate_vps)
            else:
                if q[key]>0:
                    unserved[key]+=1
                flow_interrupt+=group.arrival_rate_vps
        area+=q["minor"]+q["major"]
        peak=max(peak,q["minor"]+q["major"])
        spill+=max(0.0,q["minor"]-CRITICAL_STORAGE_RATIO*minor.storage_capacity_vehicles)
        spill+=max(0.0,q["major"]-CRITICAL_STORAGE_RATIO*major.storage_capacity_vehicles)
    max_wait=max(minor.max_wait_seconds+unserved["minor"],major.max_wait_seconds+unserved["major"])
    total=(QUEUE_AREA_WEIGHT*area+MAX_WAIT_WEIGHT*max_wait+SPILLBACK_WEIGHT*spill+
           FLOW_INTERRUPTION_WEIGHT*flow_interrupt+TRANSITION_WEIGHT*TRANSITION_OVERHEAD_SECONDS)
    return CandidateMetrics(sequence="minor_first" if minor_first else "major_first",
        queue_area_vehicle_seconds=area,peak_combined_queue=peak,
        spillback_exposure_vehicle_seconds=spill,max_wait_proxy_seconds=max_wait,
        flow_interruption_proxy=flow_interrupt,
        transition_overhead_seconds=TRANSITION_OVERHEAD_SECONDS,
        analysis_first_window_seconds=first_window,total_cost=total)

def _result(snapshot,state,reason,preferred,major=None,minor=None,x=None,clear=None,
            feasible=False,minor_candidate=None,major_candidate=None,gain=None):
    payload={
        "algorithm":"dynamic_clear_first_v1","source_id":snapshot.source_id,
        "intersection_code":snapshot.intersection_code,"frame_sequence":snapshot.frame_sequence,
        "queue_epoch":str(snapshot.queue_epoch),
        "approaches":[a.model_dump(mode="json") for a in snapshot.approaches]
    }
    state_sha=fingerprint(payload)
    body={
        "schema_version":1,"algorithm":"dynamic_clear_first_v1","cost_model":"continuity_queue_cost_v1",
        "origin":snapshot.data_origin if snapshot.data_origin!="local_authorized" else "observed",
        "source_id":snapshot.source_id,"intersection_code":snapshot.intersection_code,
        "frame_sequence":snapshot.frame_sequence,"state_sha256":state_sha,
        "state":state,"reason":reason,
        "major_group":major.model_dump(mode="json") if major else None,
        "minor_group":minor.model_dump(mode="json") if minor else None,
        "dynamic_x_safe_vehicles":x,"minor_clearance_seconds":clear,
        "minor_clearance_feasible":feasible,"preferred_in_simulation":preferred,
        "material_gain_pct":gain,
        "minor_first":minor_candidate.model_dump(mode="json") if minor_candidate else None,
        "major_first":major_candidate.model_dump(mode="json") if major_candidate else None,
        "horizon_seconds":HORIZON_SECONDS,"critical_storage_ratio":CRITICAL_STORAGE_RATIO,
        "minimum_confidence":MINIMUM_CONFIDENCE,
        "engineering_weights_validated":False,"operationally_validated":False,
        "physical_actuation":False,"operational_decision":"abstain"
    }
    body["result_sha256"]=fingerprint(body)
    return OptimizationResult.model_validate(body)

def evaluate(snapshot):
    groups=aggregate_groups(snapshot)
    if len(groups)!=2:
        return _result(snapshot,"abstain","requires_two_service_groups","abstain")
    major,minor=_major_minor(groups)
    if min(major.observation_confidence,minor.observation_confidence)<MINIMUM_CONFIDENCE:
        return _result(snapshot,"abstain","insufficient_observation_confidence","abstain",major,minor)
    x_safe,clear_time=dynamic_x_safe(minor,major)
    if clear_time is None:
        return _result(snapshot,"simulation_preference","no_net_minor_clearance","major_first",
                       major,minor,x_safe,None,False)
    first_window=min(MAX_FIRST_WINDOW_SECONDS,max(1.0,clear_time))
    minor_candidate=_simulate(minor,major,True,first_window)
    major_candidate=_simulate(minor,major,False,first_window)
    feasible=(minor.queue_length<=x_safe and clear_time+TRANSITION_OVERHEAD_SECONDS<=HORIZON_SECONDS
              and clear_time<=MAX_FIRST_WINDOW_SECONDS)
    if not feasible:
        return _result(snapshot,"simulation_preference","minor_exceeds_dynamic_x","major_first",
                       major,minor,x_safe,clear_time,False,minor_candidate,major_candidate)
    minor_gain=(major_candidate.total_cost-minor_candidate.total_cost)/max(major_candidate.total_cost,1e-9)
    major_gain=(minor_candidate.total_cost-major_candidate.total_cost)/max(minor_candidate.total_cost,1e-9)
    if minor_gain>=MATERIAL_GAIN_RATIO:
        return _result(snapshot,"simulation_preference","minor_first_lower_cost","minor_first",
                       major,minor,x_safe,clear_time,True,minor_candidate,major_candidate,100*minor_gain)
    if major_gain>=MATERIAL_GAIN_RATIO:
        return _result(snapshot,"simulation_preference","major_first_lower_cost","major_first",
                       major,minor,x_safe,clear_time,True,minor_candidate,major_candidate,-100*major_gain)
    return _result(snapshot,"simulation_preference","no_material_advantage","no_material_advantage",
                   major,minor,x_safe,clear_time,True,minor_candidate,major_candidate,
                   100*(major_candidate.total_cost-minor_candidate.total_cost)/max(major_candidate.total_cost,1e-9))
