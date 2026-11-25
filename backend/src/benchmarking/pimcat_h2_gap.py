"""RP08 offline protected gap study; C2 source preserved, no runtime imports."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from random import Random
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking.si11d_sumo import ensure_version, write_xml, VERSION
from src.benchmarking.pimcat_local import PED_LIMIT, VEH_LIMIT
from src.benchmarking.pimcat_midblock import assess
from src.benchmarking.si11c_predictive_x import observed
from src.optimization.engine import evaluate
from src.validation.io import sha256_file
from src.benchmarking.pimcat_c2_sumo import choose as c2_choose
from src.benchmarking.pimcat_d_sumo import forecast,VMAX

HORIZON=600
SEEDS=tuple(range(10100,10104))
POLICIES=("actuated","compatible","predictive_xp","gap_guarded")
# total per direction A, B one-way, pedestrians, pattern
FAMILIES={
    "mid_sparse":("mid",.025,0,.035,"steady"),
    "mid_burst":("mid",.10,0,.065,"burst"),
    "mid_slow":("mid",.14,0,.12,"slow"),
    "cross_sparse":("cross",.025,.045,.04,"steady"),
    "cross_burst":("cross",.14,.11,.09,"burst"),
    "cross_deadlines":("cross",.30,.32,.20,"slow"),
}


def network(root,kind):
    root.mkdir(parents=True,exist_ok=True)
    nodes=ET.Element("nodes")
    points={"W":(-650,0),"E":(650,0),"J":(0,0)}
    if kind=="cross":
        points.update({"S":(0,-650),"N":(0,650),"PS":(35,-35),"PN":(35,35)})
    else:
        points.update({"PS":(0,-35),"PN":(0,35)})
    for n,(x,y) in points.items():
        ET.SubElement(nodes,"node",id=n,x=str(x),y=str(y),type="traffic_light" if n=="J" else "priority")
    edges=ET.Element("edges")
    movements=[("wi","W","eo","E","A"),("ei","E","wo","W","A")]
    if kind=="cross":movements.append(("si","S","no","N","B"))
    for incoming,start,outgoing,end,_ in movements:
        for eid,f,t in ((incoming,start,"J"),(outgoing,"J",end)):
            ET.SubElement(edges,"edge",id=eid,attrib={"from":f,"to":t,
                "numLanes":"1","speed":"13.89","disallow":"pedestrian"})
    for eid,f,t in (("pi","PS","J"),("po","J","PN")):
        ET.SubElement(edges,"edge",id=eid,attrib={"from":f,"to":t,"numLanes":"1",
            "allow":"pedestrian","speed":"5","width":"3","spreadType":"center"})
    cons=ET.Element("connections")
    for incoming,_,outgoing,_,_ in movements:
        ET.SubElement(cons,"connection",attrib={"from":incoming,"to":outgoing,"fromLane":"0","toLane":"0"})
    ET.SubElement(cons,"crossing",node="J",edges="ei eo",width="4")
    for name,tree in (("nodes",nodes),("edges",edges),("connections",cons)):
        write_xml(root/(name+".xml"),tree)
    exe=shutil.which("netconvert")
    if not exe:raise RuntimeError("netconvert unavailable")
    net=root/"network.net.xml"
    p=subprocess.run([exe,"--node-files",str(root/"nodes.xml"),"--edge-files",str(root/"edges.xml"),
        "--connection-files",str(root/"connections.xml"),"--no-turnarounds","true",
        "--output-file",str(net)],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr)
    tree=ET.parse(net).getroot()
    crossings=[e for e in tree.findall("edge") if e.get("function")=="crossing"]
    assert len(crossings)==1, "expected a single explicit crossing"
    crossing=crossings[0].get("id")
    clane=crossings[0].find("lane")
    junction=tree.find("./junction[@id='J']")
    internal=junction.get("intLanes").split()
    requests={int(q.get("index")):q.get("foes") for q in junction.findall("request")}
    # Derive physical request indices from internal lanes, not TLS string positions.
    ci=internal.index(clane.get("id"))
    links={}
    groups={}
    for incoming,_,outgoing,_,g in movements:
        c=tree.find(f"./connection[@from='{incoming}'][@to='{outgoing}']")
        assert c is not None and c.get("tl")=="J"
        idx=int(c.get("linkIndex"))
        assert idx not in links
        links[idx]=internal.index(c.get("via"))
        groups[idx]=g
    pc=[c for c in tree.findall("connection") if c.get("tl")=="J" and c.get("to")==crossing]
    assert pc, "crossing not controlled by TLS"
    for c in pc:
        idx=int(c.get("linkIndex"))
        assert idx not in links
        links[idx]=ci;groups[idx]="P"
    length=len(tree.find("./tlLogic[@id='J']/phase").get("state"))
    assert set(links)==set(range(length)), "unclassified TLS index"
    def foe(i,j):
        a,b=links[i],links[j]
        return requests[a][-1-b]=="1" or requests[b][-1-a]=="1"
    for i,g in groups.items():
        for j,h in groups.items():
            if i>=j:continue
            expected={g,h} in ({"A","B"},{"A","P"})
            assert foe(i,j)==expected, f"unexpected conflict {g}/{h}"
    pi_length=float(tree.find("./edge[@id='pi']/lane").get("length"))
    return net,{"crossing":crossing,"crossing_length":float(clane.get("length")),
        "walkingareas":[e.get("id") for e in tree.findall("edge") if e.get("function")=="walkingarea"],
        "internal":internal,"groups":groups,"movements":movements,"pi_length":pi_length,
        "conflicts_verified":True}


def demand(family,seed):
    kind,a,b,p,pattern=FAMILIES[family]
    rng=Random(seed);rows=[]
    for t in range(HORIZON):
        for route,rate in (("wi",a),("ei",a),("si",b)):
            rate=rate*(1.9 if t%100<40 else .12) if pattern=="burst" else rate
            if rng.random()<rate:rows.append((t,route,f"v{t}_{route}",0))
        prob=p*(1.8 if t%80<35 else .2) if pattern=="burst" else p
        if (pattern=="single" and t==45) or rng.random()<prob:
            speed=.4 if pattern=="slow" and rng.random()<.3 else (.9 if rng.random()<.5 else 1.2)
            rows.append((t,"P",f"p{t}",speed))
    return rows


def routes(path,meta,rows):
    root=ET.Element("routes")
    ET.SubElement(root,"vType",id="car",length="5",minGap="2.5",sigma="0",speedFactor="1",speedDev="0",maxSpeed="13.89")
    ET.SubElement(root,"vType",id="walker",vClass="pedestrian",speedFactor="1",speedDev="0",maxSpeed="1.2")
    for incoming,_,outgoing,_,_ in meta["movements"]:
        ET.SubElement(root,"route",id=incoming,edges=incoming+" "+outgoing)
    for t,r,ident,speed in rows:
        if r=="P":
            person=ET.SubElement(root,"person",id=ident,type="walker",depart=str(t),
                departPos=str(max(0,meta["pi_length"]-3)))
            ET.SubElement(person,"walk",edges="pi po",speed=str(speed),arrivalPos="3")
        else:
            ET.SubElement(root,"vehicle",id=ident,type="car",route=r,depart=str(t),departSpeed="0")
    write_xml(path,root)


def gap_bound(now,distances,boundary,available=True):
    """Earliest modeled conflicting approach arrival; not a safety certificate."""
    if not available or boundary is None:return None
    values=[boundary,*distances]
    if any(v is None or not math.isfinite(v) or v<0 for v in values):return None
    distance=min(values)
    if distance==0:return 0
    cohort=forecast(now,1,distance)
    return max(0,min(cohort.earliest-now,math.floor(distance/VMAX))-1)


def gap_available(family,t):
    return not(family in ("mid_slow","cross_deadlines") and (180<=t<240 or 420<=t<450))


def choose(policy,kind,phase,age,t,qs,ages,waiting,oldest,rates,clearance,bound):
    base,reason=c2_choose("compatible" if policy=="gap_guarded" else policy,kind,phase,age,t,qs,ages,waiting,oldest,rates,clearance)
    if policy!="gap_guarded" or not waiting or age<12 or t%5 or phase!="A":
        return base,reason
    if bound is None:return base,"gap_unknown_"+reason
    if reason in ("compatible","pedestrian_deadline","competing_vehicle_deadline","vehicle_deadline") or t-oldest>=PED_LIMIT-20 or max(ages)>=VEH_LIMIT-20:
        return base,reason
    need=5+10+clearance+5+3
    if bound>=need:
        return ("BP" if kind=="cross" else "P"),"gap_candidate"
    if reason=="low_conflicting_demand" and base in ("P","BP"):
        return phase,"gap_defer"
    return base,reason


def trajectory(api,net,meta,route,rows,family,seed,policy):
    kind,a,b,p,_=FAMILIES[family];rates=(2*a,b,p)
    groups=meta["groups"];cross=meta["crossing"]
    clear=math.ceil(1+meta["crossing_length"]/.6)+1
    veh_lanes={g:[i+"_0" for i,_,_,_,h in meta["movements"] if h==g] for g in ("A","B")}
    internal=set(meta["internal"])
    planned={x[2]:x for x in rows};scheduled=set();entered=set();done=set()
    p_entered=set();p_done=set();requested={};admitted={};completed=set()
    waits={};ped_wait={};active=set();persons=set();crossing=set();late_p=set()
    area_v=area_p=critical=0.;pending_v_ticks=0
    changes=empty_p=compatible_entries=extensions=0
    moving=set();was_stopped=set();stops={};a_stops=0;overspeed=0
    gap_choices=gap_deferred=gap_unknown_reviews=0
    episode=None;episodes=[]
    collisions=teleports=conflict=red_entries=unobserved=0
    phase="A";start=0;mode="active";target="A";trans_start=0
    plans=[];green_ticks={"A":0,"B":0,"P":0};vehicle_internal=set()
    actual=""
    def signal(vgroups=(),p_open=False,yellow=False):
        return "".join(("G" if p_open else "r") if groups[i]=="P" else
            ("y" if yellow else "G") if groups[i] in vgroups else "r" for i in range(len(groups)))
    def vgroup(ph):return ("B",) if ph in ("B","BP") else ("A",) if ph=="A" else ()
    def switch(next_phase,t,reason):
        nonlocal target,mode,trans_start,changes,episode,gap_choices
        target=next_phase;mode="transition";trans_start=t;changes+=1
        plans.append({"tick":t,"from":phase,"to":target,"reason":reason})
        if target in ("P","BP"):
            assert episode is None
            episode={"start":t,"reason":reason,"new_A_stops":0}
            gap_choices+=int(reason=="gap_candidate")
    api.start(["sumo","-n",str(net),"-r",str(route),"--seed",str(seed),"--step-length","1",
        "--route-steps","0","--time-to-teleport","-1","--max-depart-delay","-1",
        "--collision.action","warn","--pedestrian.model","striping",
        "--no-step-log","true","--duration-log.disable","true","--end",str(HORIZON)])
    try:
        actual=api.getVersion()[1]
        assert actual.split()[-1]==VERSION and tuple(api.trafficlight.getIDList())==("J",)
        assert len(api.trafficlight.getRedYellowGreenState("J"))==len(groups)
        caps={lane:max(1,math.floor(api.lane.getLength(lane)/7.5)) for lanes in veh_lanes.values() for lane in lanes}
        by_time={}
        for row in rows:by_time.setdefault(row[0],[]).append(row[2])
        for t in range(HORIZON):
            waiting=set(requested)-set(admitted)
            oldest=min((requested[i] for i in waiting),default=None)
            q=[];ages=[]
            for g in ("A","B"):
                ids=[i for lane in veh_lanes[g] for i in api.lane.getLastStepVehicleIDs(lane)
                     if i in active and api.vehicle.getSpeed(i)<.1]
                q.append(len(ids));ages.append(max((waits.get(i,0) for i in ids),default=0))
            if mode=="active":
                if phase in ("P","BP"):
                    if t-start>=10+clear:
                        if crossing:extensions+=1
                        else:
                            nxt="A"
                            if kind=="cross" and policy!="fixed":
                                nxt="B" if q[1]>q[0] and q[1] else "A"
                            switch(nxt,t,"pedestrian_clearance_complete")
                else:
                    distances=[max(0,api.lane.getLength(lane)-api.vehicle.getLanePosition(k))
                        for lane in veh_lanes["A"] for k in api.lane.getLastStepVehicleIDs(lane) if k in active]
                    boundary=min(api.lane.getLength(lane) for lane in veh_lanes["A"])
                    bound=gap_bound(t,distances,boundary,gap_available(family,t)) if not vehicle_internal else 0
                    nxt,reason=choose(policy,kind,phase,t-start,t,q,ages,len(waiting),oldest,rates,clear,bound)
                    gap_deferred+=int(reason=="gap_defer")
                    gap_unknown_reviews+=int(reason.startswith("gap_unknown_"))
                    if nxt!=phase:switch(nxt,t,reason)
            if mode=="transition":
                elapsed=t-trans_start
                if elapsed>=5 and not vehicle_internal and not crossing:
                    phase=target;start=t;mode="active"
                    if phase not in ("P","BP") and episode is not None:
                        episode["end"]=t;episodes.append(episode);episode=None
                    if phase in ("P","BP") and not waiting:empty_p+=1
                else:
                    state=signal(vgroup(phase),yellow=True) if elapsed<3 else signal()
            if mode=="active":
                state=signal(vgroup(phase),phase in ("P","BP") and t-start<10)
            p_green=any(state[i]=="G" for i,g in groups.items() if g=="P")
            a_open=any(state[i] in "Gy" for i,g in groups.items() if g=="A")
            if (p_green or crossing) and a_open:conflict+=1
            assert not ((p_green or crossing) and a_open),"conflicting signal/occupancy"
            for g in green_ticks:
                green_ticks[g]+=int(any(state[i]=="G" for i,h in groups.items() if h==g))
            scheduled.update(by_time.get(t,()))
            api.trafficlight.setRedYellowGreenState("J",state)
            assert api.trafficlight.getRedYellowGreenState("J")==state
            api.simulationStep()
            new=set(api.simulation.getDepartedIDList());finished=set(api.simulation.getArrivedIDList())
            pn=set(api.simulation.getDepartedPersonIDList());pf=set(api.simulation.getArrivedPersonIDList())
            assert not (new&entered or finished&done or pn&p_entered or pf&p_done)
            assert (new|pn)<=scheduled
            entered.update(new);done.update(finished);p_entered.update(pn);p_done.update(pf)
            active=set(api.vehicle.getIDList());persons=set(api.person.getIDList())
            assert active==entered-done and persons==p_entered-p_done
            assert done<=entered and p_done<=p_entered
            vehicle_internal={i for i in active if api.vehicle.getLaneID(i) in internal}
            previous_crossing=crossing
            crossing={i for i in persons if api.person.getRoadID(i)==cross}
            completed.update(previous_crossing-crossing)
            for ident in crossing-previous_crossing:
                assert ident not in admitted
                if ident not in requested:
                    requested[ident]=t+1;unobserved+=1
                admitted[ident]=t+1
                ped_wait[ident]=t+1-requested[ident]
                if ped_wait[ident]>PED_LIMIT:late_p.add(ident)
                if not p_green:red_entries+=1
                assert p_green,"pedestrian entry sampled during red"
                compatible_entries+=int(phase=="BP" and mode=="active")
            for ident in persons-set(admitted):
                if (api.person.getRoadID(ident) in meta["walkingareas"]
                    and api.person.getNextEdge(ident)==cross):
                    requested.setdefault(ident,t+1)
            assert p_done<=completed, "pedestrian arrived without traversing crossing"
            waiting=set(requested)-set(admitted)
            for ident in waiting:
                if t+1-requested[ident]>PED_LIMIT:late_p.add(ident)
            pending={i for i in scheduled-entered if planned[i][1]!="P"}
            halted={i for i in active if api.vehicle.getSpeed(i)<.1}
            for ident in pending|halted:waits[ident]=waits.get(ident,0)+1
            for ident in active:
                v=api.vehicle.getSpeed(ident);overspeed+=int(v>VMAX+.1)
                if v>=.1:moving.add(ident);was_stopped.discard(ident)
                elif ident in moving and ident not in was_stopped:
                    stops[ident]=stops.get(ident,0)+1;was_stopped.add(ident)
                    if planned[ident][1] in ("wi","ei"):
                        a_stops+=1
                        if episode is not None:episode["new_A_stops"]+=1
            area_v+=len(pending)+len(halted);pending_v_ticks+=len(pending);area_p+=len(waiting)
            critical+=sum(max(0,api.lane.getLastStepVehicleNumber(l)-.85*c) for l,c in caps.items())
            collisions+=api.simulation.getCollidingVehiclesNumber()
            teleports+=api.simulation.getStartingTeleportNumber()
        assert scheduled==set(planned)
        p_total=sum(row[1]=="P" for row in rows);v_total=len(rows)-p_total
        assert p_total==len(p_entered)+len(set(planned)-entered-p_entered)-(v_total-len(entered))
        assert len(admitted)==len(completed)+len(crossing)
        assert len(requested)==len(admitted)+len(waiting)
        assert not collisions and not teleports and not conflict and not red_entries and not overspeed
        percentile=lambda seq:sorted(seq)[math.ceil(.95*len(seq))-1] if seq else None
        return {"runtime_version":actual,"vehicles_scheduled":v_total,"vehicles_inserted":len(entered),
            "vehicles_exited":len(done),"vehicles_remaining":len(active),"vehicles_uninserted":v_total-len(entered),
            "pedestrians_scheduled":p_total,"pedestrians_inserted":len(p_entered),"pedestrians_exited":len(p_done),
            "pedestrians_uninserted":p_total-len(p_entered),"pedestrians_remaining":len(persons),
            "pedestrians_requested":len(requested),"pedestrians_admitted":len(admitted),
            "pedestrians_completed":len(completed),"pedestrians_waiting":len(waiting),
            "pedestrians_crossing":len(crossing),"pedestrians_unobserved_before_entry":unobserved,
            "vehicle_area":area_v,"pedestrian_area":area_p,"person_area":1.5*area_v+area_p,
            "pending_vehicle_seconds":pending_v_ticks,"critical_exposure":critical,
            "vehicle_max_wait":max(waits.values(),default=0),
            "pedestrian_max_wait":max(list(ped_wait.values())+[HORIZON-requested[i] for i in waiting],default=0),
            "vehicle_p95_exited":percentile([waits.get(i,0) for i in done]),
            "pedestrian_p95_admitted":percentile(list(ped_wait.values())),
            "vehicle_deadline_violations":sum(x>VEH_LIMIT for x in waits.values()),
            "pedestrian_deadline_violations":len(late_p),"pedestrian_on_time_admitted":sum(w<=PED_LIMIT for w in ped_wait.values()),
            "phase_changes":changes,"empty_pedestrian_phases":empty_p,"compatible_admissions":compatible_entries,
            "extension_ticks":extensions,"green_ticks":green_ticks,"colliding_vehicle_events":collisions,
            "teleports":teleports,"conflict_violations":conflict,"red_entries":red_entries,"plans":plans,
            "clearance_minimum_seconds":clear,"overspeed_samples":overspeed,
            "a_stops":a_stops,"all_stops":sum(stops.values()),"mean_stops_completed":fmean(stops.get(k,0) for k in done) if done else None,
            "gap_choices":gap_choices,"gap_deferred":gap_deferred,"gap_unknown_reviews":gap_unknown_reviews,
            "protected_episodes_complete":len(episodes),"protected_episodes_zero_new_A_stops":sum(x["new_A_stops"]==0 for x in episodes),
            "protected_episodes_censored":int(episode is not None),"episodes":episodes}
    finally:api.close()


def case(api,root,family,seed,policies=POLICIES):
    kind=FAMILIES[family][0]
    net,meta=network(root,kind)
    rows=demand(family,seed)
    route=root/"demand.rou.xml";routes(route,meta,rows)
    return {"family":family,"topology":kind,"seed":seed,"network_sha256":hashlib.sha256(ET.canonicalize(from_file=net,with_comments=False).encode("utf-8")).hexdigest(),
        "demand_sha256":sha256_file(route),"crossing_length_m":meta["crossing_length"],
        "conflicts_verified":meta["conflicts_verified"],
        "metrics":{p:trajectory(api,net,meta,route,rows,family,seed,p) for p in policies}}


FIELDS=("person_area","vehicle_area","pedestrian_area","vehicle_max_wait","pedestrian_max_wait",
    "critical_exposure","vehicles_exited","pedestrians_completed","pedestrian_deadline_violations",
    "vehicle_deadline_violations","vehicles_uninserted","pedestrians_admitted","pedestrians_requested",
    "pedestrians_scheduled","pedestrians_waiting","pedestrians_uninserted","compatible_admissions",
    "extension_ticks","empty_pedestrian_phases","phase_changes","pending_vehicle_seconds","a_stops","all_stops","gap_choices","gap_deferred","gap_unknown_reviews","protected_episodes_complete","protected_episodes_zero_new_A_stops","protected_episodes_censored")


def summarize(rows):
    out={}
    for p in POLICIES:
        ms=[r["metrics"][p] for r in rows]
        d={k:fmean(m[k] for m in ms) for k in FIELDS}
        for k in ("vehicle_max_wait","pedestrian_max_wait"):d["worst_"+k]=max(m[k] for m in ms)
        for k in ("vehicle_deadline_violations","pedestrian_deadline_violations","pedestrians_scheduled",
            "pedestrians_admitted","pedestrian_on_time_admitted","compatible_admissions","pedestrians_completed",
            "colliding_vehicle_events","teleports","conflict_violations","red_entries"):
            d["total_"+k]=sum(m[k] for m in ms)
        for k in ("vehicle_p95_exited","pedestrian_p95_admitted"):
            values=[m[k] for m in ms if m[k] is not None]
            d["mean_case_"+k]=fmean(values) if values else None
        d["occupancy_sensitivity"]={str(o):o*d["vehicle_area"]+d["pedestrian_area"] for o in (1,1.5,2)}
        out[p]=d
    return out


def gate(summary,candidate):
    c=summary[candidate];checks={}
    for baseline in ("compatible","predictive_xp"):
        b=summary[baseline]
        checks[baseline]={**{k:c[k]<=1.05*b[k] for k in ("person_area","vehicle_area","pedestrian_area",
            "worst_vehicle_max_wait","worst_pedestrian_max_wait","critical_exposure","a_stops")},
            **{k:c[k]>=.95*b[k] for k in ("vehicles_exited","pedestrians_completed")},
            **{k:c[k]<=b[k] for k in ("total_pedestrian_deadline_violations","total_vehicle_deadline_violations",
                "vehicles_uninserted")}}
    return {"passed":all(v for group in checks.values() for v in group.values()),"checks":checks}


def run():
    api=ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-h2-") as d:
        rows=[case(api,Path(d)/f"{f}-{s}",f,s) for f in FAMILIES for s in SEEDS]
    groups={"overall":rows,"mid":[r for r in rows if r["topology"]=="mid"],
        "cross":[r for r in rows if r["topology"]=="cross"],
        "stress":[r for r in rows if r["family"] in ("mid_slow","cross_deadlines")]}
    summaries={k:summarize(v) for k,v in groups.items()}
    families={f:summarize([r for r in rows if r["family"]==f]) for f in FAMILIES}
    g={k:gate(summaries[k],"gap_guarded") for k in ("mid","cross","stress")}
    g["directional_stop_reduction"]=summaries["overall"]["gap_guarded"]["a_stops"]<summaries["overall"]["compatible"]["a_stops"]
    g["passed"]=g["directional_stop_reduction"] and all(g[k]["passed"] for k in ("mid","cross","stress"))
    d={"scope":"pimcat_h2_protected_gap_synthetic_not_field","sumo_version":VERSION,
        "cases":len(rows),"trajectories":len(rows)*len(POLICIES),"horizon_seconds":HORIZON,
        "seeds":list(SEEDS),"policies":list(POLICIES),"summaries":summaries,"families":families,"gates":{"gap_guarded":g},"rows":rows,
        "research_gate_passed":g["passed"],"c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION",
        "real_gap_calibration":"NOT_RUN","candidate_promoted":False,"physical_actuation":False,
        "operationally_validated":False,"commercial_demo_authorized":False,"operational_decision":"abstain"}
    d["result_sha256"]=fingerprint(d);return d


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    d=run()
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False)


if __name__=="__main__":main()
