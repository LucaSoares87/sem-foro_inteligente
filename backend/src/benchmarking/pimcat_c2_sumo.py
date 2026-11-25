"""Offline microscopic pedestrian study, never imported by the application."""
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

HORIZON=360
SEEDS=tuple(range(7100,7104))
POLICIES=("fixed","actuated","compatible","proportional","predictive_xp","predictive_xp_xv")
# total per direction A, B one-way, pedestrians, pattern
FAMILIES={
    "mid_empty":("mid",.18,0,0,"steady"),
    "mid_single":("mid",.22,0,0,"single"),
    "mid_burst":("mid",.16,0,.16,"burst"),
    "mid_slow":("mid",.33,0,.22,"slow"),
    "cross_light":("cross",.08,.10,.04,"steady"),
    "cross_compatible":("cross",.10,.32,.16,"burst"),
    "cross_heavy":("cross",.30,.35,.16,"steady"),
    "cross_deadlines":("cross",.42,.48,.35,"slow"),
}


def network(root,kind):
    root.mkdir(parents=True,exist_ok=True)
    nodes=ET.Element("nodes")
    points={"W":(-180,0),"E":(180,0),"J":(0,0)}
    if kind=="cross":
        points.update({"S":(0,-180),"N":(0,180),"PS":(35,-35),"PN":(35,35)})
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
            if rng.random()<rate:rows.append((t,route,f"v{t}_{route}",0))
        prob=p*(1.8 if t%80<35 else .2) if pattern=="burst" else p
        if (pattern=="single" and t==45) or rng.random()<prob:
            speed=.4 if pattern=="slow" and rng.random()<.3 else (.9 if rng.random()<.5 else 1.2)
            rows.append((t,"P",f"p{t}",speed))
    return rows


def routes(path,meta,rows):
    root=ET.Element("routes")
    ET.SubElement(root,"vType",id="car",length="5",minGap="2.5",sigma="0",speedFactor="1",maxSpeed="13.89")
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


def choose(policy,kind,phase,age,t,qs,ages,waiting,oldest,rates,clearance):
    """At eligible review, return proposed phase using present observations only."""
    a,b,p=rates
    if policy=="fixed":
        if age<25:return phase,"fixed_hold"
        return ("P" if kind=="mid" or phase=="B" else "B"),"fixed"
    if age<12 or t%5:return phase,"minimum_or_review"
    if kind=="mid":
        rr=assess(now=t,waiting="demand" if waiting else "empty",crossing="clear",phase="vehicle",
            topology_confirmed=True,clearance_complete=True,oldest_request=oldest)
        assert rr.operational_decision=="abstain" and not rr.physical_actuation
        if rr.preference_in_simulation=="hold_vehicle_preference":return "A","rp07_hold"
        base="A"
    else:
        base=phase
        if qs[0] or qs[1]:
            scores=(qs[0]+15*a,qs[1]+15*b)
            base="A" if scores[0]>scores[1] else "B" if scores[1]>scores[0] else phase
            if not qs[0]:base="B"
            elif not qs[1]:base="A"
            elif policy=="predictive_xp_xv" and max(qs)<=200:
                pair=((0,min(1,a),.5,40),(0,min(1,b),.5,24))
                q=[deque([max(0,t-ages[g])]*qs[g]) for g in (0,1)]
                x=evaluate(observed(pair,q,t))
                assert x.operational_decision=="abstain" and not x.physical_actuation
                if x.preferred_in_simulation in ("minor_first","major_first"):
                    group=x.minor_group if x.preferred_in_simulation=="minor_first" else x.major_group
                    base=group.group_id
        if age>=45 and qs[int(phase=="A")]:base="B" if phase=="A" else "A"
    urgent=[g for g in range(2 if kind=="cross" else 1) if ages[g]>=VEH_LIMIT-20]
    if urgent:base="AB"[max(urgent,key=lambda g:ages[g])]
    if not waiting:return base,"vehicle_demand"
    pw=t-oldest
    carona=kind=="cross" and policy!="actuated"
    if carona and base=="B":return "BP","compatible"
    if pw>=PED_LIMIT-20:
        if urgent and VEH_LIMIT-max(ages[g] for g in urgent)<PED_LIMIT-pw:
            return base,"competing_vehicle_deadline"
        return ("BP" if carona else "P"),"pedestrian_deadline"
    if urgent:return base,"vehicle_deadline"
    if policy=="actuated":return "P","request"
    if not qs[0]:return ("BP" if carona else "P"),"low_conflicting_demand"
    if policy=="compatible":return base,"await_compatible"
    if policy=="proportional":
        serve=waiting>=1.5*qs[0]
    else:
        d=10+clearance
        cost=1.5*d*(qs[0]+a*d/2)
        threshold=max(1,math.ceil(cost/(15*(1+pw/PED_LIMIT))-p*15/2))
        serve=waiting>=threshold
    return (("BP" if carona else "P"),"advance_request") if serve else (base,"defer_request")


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
    collisions=teleports=conflict=red_entries=unobserved=0
    phase="A";start=0;mode="active";target="A";trans_start=0
    plans=[];green_ticks={"A":0,"B":0,"P":0};vehicle_internal=set()
    actual=""
    def signal(vgroups=(),p_open=False,yellow=False):
        return "".join(("G" if p_open else "r") if groups[i]=="P" else
            ("y" if yellow else "G") if groups[i] in vgroups else "r" for i in range(len(groups)))
    def vgroup(ph):return ("B",) if ph in ("B","BP") else ("A",) if ph=="A" else ()
    def switch(next_phase,t,reason):
        nonlocal target,mode,trans_start,changes
        target=next_phase;mode="transition";trans_start=t;changes+=1
        plans.append({"tick":t,"from":phase,"to":target,"reason":reason})
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
                    nxt,reason=choose(policy,kind,phase,t-start,t,q,ages,len(waiting),oldest,rates,clear)
                    if nxt!=phase:switch(nxt,t,reason)
            if mode=="transition":
                elapsed=t-trans_start
                if elapsed>=5 and not vehicle_internal and not crossing:
                    phase=target;start=t;mode="active"
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
            area_v+=len(pending)+len(halted);pending_v_ticks+=len(pending);area_p+=len(waiting)
            critical+=sum(max(0,api.lane.getLastStepVehicleNumber(l)-.85*c) for l,c in caps.items())
            collisions+=api.simulation.getCollidingVehiclesNumber()
            teleports+=api.simulation.getStartingTeleportNumber()
        assert scheduled==set(planned)
        p_total=sum(row[1]=="P" for row in rows);v_total=len(rows)-p_total
        assert p_total==len(p_entered)+len(set(planned)-entered-p_entered)-(v_total-len(entered))
        assert len(admitted)==len(completed)+len(crossing)
        assert len(requested)==len(admitted)+len(waiting)
        assert not collisions and not teleports and not conflict and not red_entries
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
            "clearance_minimum_seconds":clear}
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
    "extension_ticks","empty_pedestrian_phases","phase_changes","pending_vehicle_seconds")


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
    for baseline in ("compatible","proportional"):
        b=summary[baseline]
        checks[baseline]={**{k:c[k]<=1.05*b[k] for k in ("person_area","vehicle_area","pedestrian_area",
            "worst_vehicle_max_wait","worst_pedestrian_max_wait","critical_exposure")},
            **{k:c[k]>=.95*b[k] for k in ("vehicles_exited","pedestrians_completed")},
            **{k:c[k]<=b[k] for k in ("total_pedestrian_deadline_violations","total_vehicle_deadline_violations",
                "vehicles_uninserted")}}
    return {"passed":all(v for group in checks.values() for v in group.values()),"checks":checks}


def run():
    api=ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-c2-") as d:
        rows=[case(api,Path(d)/f"{f}-{s}",f,s) for f in FAMILIES for s in SEEDS]
    groups={"overall":rows,"mid":[r for r in rows if r["topology"]=="mid"],
        "cross":[r for r in rows if r["topology"]=="cross"],
        "stress":[r for r in rows if r["family"] in ("mid_slow","cross_deadlines")]}
    summaries={k:summarize(v) for k,v in groups.items()}
    families={f:summarize([r for r in rows if r["family"]==f]) for f in FAMILIES}
    for r in rows:
        if r["family"]=="mid_empty":
            assert all(r["metrics"][p]["phase_changes"]==0 for p in POLICIES[1:])
        if r["family"]=="mid_single":
            assert all(r["metrics"][p]["pedestrians_completed"]==1 and
                r["metrics"][p]["pedestrian_deadline_violations"]==0 for p in POLICIES[1:])
    gates={}
    for candidate in POLICIES[-2:]:
        g={k:gate(summaries[k],candidate) for k in ("mid","cross","stress")}
        g["improvement_vs_fixed"]=summaries["overall"][candidate]["person_area"]<summaries["overall"]["fixed"]["person_area"]
        g["passed"]=g["improvement_vs_fixed"] and all(g[k]["passed"] for k in ("mid","cross","stress"))
        gates[candidate]=g
    d={"scope":"pimcat_c2_microscopic_synthetic_not_field","sumo_version":VERSION,
        "sumo_validation":"EXECUTED_SYNTHETIC","cases":len(rows),"trajectories":len(rows)*len(POLICIES),
        "horizon_seconds":HORIZON,"seeds":list(SEEDS),"policies":list(POLICIES),
        "summaries":summaries,"families":families,"gates":gates,"rows":rows,
        "research_gate_passed":gates["predictive_xp_xv"]["passed"],
        "candidate_promoted":False,"physical_actuation":False,"operationally_validated":False,
        "commercial_demo_authorized":False,"operational_decision":"abstain",
        "perception_validation":"NOT_RUN","network_coordination":"NOT_RUN"}
    d["result_sha256"]=fingerprint(d)
    return d


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    d=run()
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False)


if __name__=="__main__":main()
