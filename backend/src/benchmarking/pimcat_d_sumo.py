"""Offline corridor experiment. Only in-process SUMO; no runtime/control interface."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from random import Random
from statistics import fmean, pstdev
from src.archive.store import fingerprint
from src.benchmarking.si11d_sumo import ensure_version, write_xml, VERSION
from src.benchmarking.pimcat_local import PED_LIMIT, VEH_LIMIT
from src.benchmarking.pimcat_midblock import assess
from src.validation.io import sha256_file

HORIZON=600
SEEDS=tuple(range(8100,8104))
POLICIES=("independent","fixed_offset","adaptive_eta","adaptive_eta_storage")
VMAX=13.89
# nodes, spacing, main arrival, cross arrival, pedestrian arrival, pattern, isolated node index
FAMILIES={
 "two_light":(2,220,.10,.10,.035,"steady",None),
 "two_platoon":(2,220,.22,.15,.06,"burst",None),
 "two_compact":(2,100,.42,.32,.12,"slow",None),
 "two_midblock":(2,220,.22,.17,.05,"single",1),
 "three_balanced":(3,220,.23,.20,.08,"steady",None),
 "three_shift":(3,220,.30,.24,.07,"shift",None),
 "three_storage":(3,100,.46,.35,.13,"slow",None),
 "three_midblock":(3,100,.24,.18,.08,"burst",1),
}


@dataclass(frozen=True)
class Cohort:
    issued:int
    count:int
    earliest:int
    nominal:int
    latest:int
    expires:int


def forecast(t,count,distance):
    if type(t) is not int or t<0 or type(count) is not int or count<=0 or not math.isfinite(distance) or distance<=0:
        raise ValueError("invalid aggregate departure observation")
    return Cohort(t,count,t+math.ceil(distance/VMAX),t+math.ceil(distance/10),
                  t+math.ceil(distance/6),t+math.ceil(distance/6)+5)


def upcoming(cohorts,t,in_transit,available=True):
    if not available:return None
    if type(t) is not int or t<0 or type(in_transit) is not int or in_transit<0:
        raise ValueError("invalid receiving observation")
    eligible=[c for c in cohorts if c.issued<=t<=c.expires and c.latest>=t and c.earliest<=t+15]
    return min(in_transit,sum(c.count for c in eligible))


def capacity_block(occupancy,capacity,queue,anticipate=False):
    if not math.isfinite(occupancy) or not math.isfinite(capacity) or capacity<=0 or occupancy<0 or queue<0:
        raise ValueError("invalid storage observation")
    return occupancy>=.85*capacity or (anticipate and occupancy>=.70*capacity and queue>=max(1,math.floor(.85*capacity-occupancy)))


def network(root,family):
    n,spacing,_,_,_,_,mid=FAMILIES[family]
    root.mkdir(parents=True,exist_ok=True)
    nodes=ET.Element("nodes");edges=ET.Element("edges");cons=ET.Element("connections")
    def node(k,x,y,kind="priority"):
        ET.SubElement(nodes,"node",id=k,x=str(x),y=str(y),type=kind)
    def edge(k,f,t,ped=False):
        attrs={"from":f,"to":t,"numLanes":"1","speed":"5" if ped else str(VMAX)}
        attrs.update({"allow":"pedestrian","width":"3","spreadType":"center"} if ped else {"disallow":"pedestrian"})
        ET.SubElement(edges,"edge",id=k,attrib=attrs)
    def connection(a,b):
        ET.SubElement(cons,"connection",attrib={"from":a,"to":b,"fromLane":"0","toLane":"0"})
    node("W",-180,0);node("E",(n-1)*spacing+180,0)
    for i in range(n):
        j=f"J{i}";x=i*spacing
        node(j,x,0,"traffic_light")
        if i!=mid:
            node(f"S{i}",x,-180);node(f"N{i}",x,180)
            edge(f"bi{i}",f"S{i}",j);edge(f"bo{i}",j,f"N{i}");connection(f"bi{i}",f"bo{i}")
        px=x if i==mid else x+35
        node(f"PS{i}",px,-35);node(f"PN{i}",px,35)
        edge(f"pi{i}",f"PS{i}",j,True);edge(f"po{i}",j,f"PN{i}",True)
    for i in range(n+1):
        edge(f"a{i}","W" if i==0 else f"J{i-1}","E" if i==n else f"J{i}")
    for i in range(n):
        connection(f"a{i}",f"a{i+1}")
        ET.SubElement(cons,"crossing",node=f"J{i}",edges=f"a{i+1}",width="4")
    for name,tree in (("nodes",nodes),("edges",edges),("connections",cons)):
        write_xml(root/(name+".xml"),tree)
    exe=shutil.which("netconvert")
    if not exe:raise RuntimeError("netconvert missing")
    net=root/"network.net.xml"
    p=subprocess.run([exe,"--node-files",str(root/"nodes.xml"),"--edge-files",str(root/"edges.xml"),
         "--connection-files",str(root/"connections.xml"),"--no-turnarounds","true",
         "--output-file",str(net)],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr)
    tree=ET.parse(net).getroot();meta=[]
    for i in range(n):
        j=f"J{i}";junction=tree.find(f"./junction[@id='{j}']")
        internal=junction.get("intLanes").split()
        requests={int(q.get("index")):q.get("foes") for q in junction.findall("request")}
        crossings=[e for e in tree.findall("edge") if e.get("function")=="crossing" and e.get("id").startswith(":"+j+"_")]
        assert len(crossings)==1, f"missing/extra crossing at {j}"
        crossing=crossings[0].get("id");clane=crossings[0].find("lane")
        ci=internal.index(clane.get("id"));groups={};links={}
        movements=[(f"a{i}",f"a{i+1}","A")]
        if i!=mid:movements.append((f"bi{i}",f"bo{i}","B"))
        for a,b,g in movements:
            c=tree.find(f"./connection[@from='{a}'][@to='{b}']")
            assert c is not None and c.get("tl")==j
            k=int(c.get("linkIndex"));assert k not in groups
            groups[k]=g;links[k]=internal.index(c.get("via"))
        pc=[c for c in tree.findall("connection") if c.get("tl")==j and c.get("to")==crossing]
        assert pc
        for c in pc:
            k=int(c.get("linkIndex"));assert k not in groups
            groups[k]="P";links[k]=ci
        length=len(tree.find(f"./tlLogic[@id='{j}']/phase").get("state"))
        assert set(groups)==set(range(length))
        for k,g in groups.items():
            for l,h in groups.items():
                if k>=l:continue
                a,b=links[k],links[l]
                foe=requests[a][-1-b]=="1" or requests[b][-1-a]=="1"
                assert foe==({g,h} in ({"A","B"},{"A","P"})),f"unexpected conflict {j}: {g}/{h}"
        meta.append({"j":j,"mid":i==mid,"groups":groups,"internal":internal,"crossing":crossing,
            "walkingareas":[e.get("id") for e in tree.findall("edge") if e.get("function")=="walkingarea" and e.get("id").startswith(":"+j+"_")],
            "pi_length":float(tree.find(f"./edge[@id='pi{i}']/lane").get("length")),
            "clear":math.ceil(1+float(clane.get("length"))/.6)+1})
    return net,meta


def demand(family,seed):
    n,_,a,b,p,pattern,mid=FAMILIES[family]
    rng=Random(seed);rows=[]
    for t in range(HORIZON):
        rate=a*(1.8 if t%90<40 else .2) if pattern=="burst" else a*(.5 if t<300 else 1.5) if pattern=="shift" else a
        if rng.random()<min(1,rate):rows.append((t,"A",f"v{t}_A",0,-1))
        for i in range(n):
            if i!=mid and rng.random()<b:rows.append((t,f"B{i}",f"v{t}_B{i}",0,i))
            if (pattern=="single" and i==mid and t==110) or (not (pattern=="single" and i==mid) and rng.random()<p):
                speed=.4 if pattern=="slow" and rng.random()<.3 else (.9 if rng.random()<.5 else 1.2)
                rows.append((t,"P",f"p{t}_{i}",speed,i))
    return rows


def routes(path,meta,rows):
    root=ET.Element("routes");n=len(meta)
    ET.SubElement(root,"vType",id="car",length="5",minGap="2.5",sigma="0",speedFactor="1",speedDev="0",maxSpeed=str(VMAX))
    ET.SubElement(root,"vType",id="walker",vClass="pedestrian",speedFactor="1",speedDev="0",maxSpeed="1.2")
    ET.SubElement(root,"route",id="A",edges=" ".join(f"a{i}" for i in range(n+1)))
    for i,m in enumerate(meta):
        if not m["mid"]:ET.SubElement(root,"route",id=f"B{i}",edges=f"bi{i} bo{i}")
    for t,r,ident,speed,i in rows:
        if r=="P":
            person=ET.SubElement(root,"person",id=ident,type="walker",depart=str(t),
                departPos=str(max(0,meta[i]["pi_length"]-3)))
            ET.SubElement(person,"walk",edges=f"pi{i} po{i}",speed=str(speed),arrivalPos="3")
        else:ET.SubElement(root,"vehicle",id=ident,type="car",route=r,depart=str(t),departSpeed="0")
    write_xml(path,root)


def choose(policy,mid,phase,age,t,qa,qb,wa,wb,p,oldest,eta,blocked,offset):
    if phase=="A" and age<12 or phase=="B" and age<12:return phase,"minimum"
    if phase!="R" and t%5:return phase,"review"
    if mid:
        rp=assess(now=t,waiting="demand" if p else "empty",crossing="clear",phase="vehicle",
            topology_confirmed=True,clearance_complete=True,oldest_request=oldest,other_obligation=blocked)
        assert rp.operational_decision=="abstain" and not rp.physical_actuation
        if rp.preference_in_simulation=="hold_vehicle_preference":return "A","rp07_hold"
    # P or BP safe only after transition and independent protection check.
    if blocked:return ("P" if mid else "BP") if p else ("R" if mid else "B"),"storage_veto"
    p_age=t-oldest if oldest is not None else -1
    urgent_a=wa>=VEH_LIMIT-20;urgent_b=not mid and wb>=VEH_LIMIT-20
    if p and p_age>=PED_LIMIT-20 and not (urgent_a and VEH_LIMIT-wa<PED_LIMIT-p_age):
        return ("P" if mid else "BP"),"pedestrian_deadline"
    if mid:
        if p and (not qa or p>=1.5*qa):return "P","request"
        return "A","rp07_wait"
    if urgent_a or urgent_b:
        base="A" if wa>=wb else "B"
        return ("BP" if base=="B" and p else base),"vehicle_deadline"
    if policy=="fixed_offset":
        base="A" if (t-offset)%70<30 else "B"
    else:
        score_a=qa+(eta or 0) if policy.startswith("adaptive") else qa
        base="A" if score_a>qb else "B" if qb>score_a else (phase if phase in ("A","B") else "A")
    if p and (base=="B" or not qa):return "BP","compatible"
    return base,"eta" if policy.startswith("adaptive") and eta else "local_or_offset"


@dataclass
class State:
    phase:str="A"
    start:int=0
    target:str="A"
    transition:int|None=None


def percentile(v):
    return sorted(v)[math.ceil(.95*len(v))-1] if v else None


def trajectory(api,net,meta,route,rows,family,seed,policy):
    n,spacing,_,_,_,_,mid=FAMILIES[family]
    states=[State() for _ in meta]
    planned={r[2]:r for r in rows};by_time=defaultdict(set)
    for r in rows:by_time[r[0]].add(r[2])
    scheduled=set();entered=set();done=set();p_entered=set();p_done=set()
    requested={};admitted={};completed=set();ped_wait={};waits=defaultdict(int)
    moving=set();was_stopped=set();stops=defaultdict(int)
    cohorts=[[] for _ in range(n)];issued={};arrived_eta={};segment_seen=[set() for _ in range(n)]
    crossings=[set() for _ in meta];internals=[set() for _ in meta]
    speed_samples=[];area_v=area_p=critical=0.;pending_ticks=0
    corridor_area=transverse_area=0;segment_critical=[0.]*n
    changes=extensions=vetoes=critical_green=critical_yellow=critical_entries=0
    collisions=teleports=overspeed=red_entries=conflict=0
    compatible=unobserved=eta_reviews=0
    green_ticks=[0]*n;mid_empty_interruptions=0
    exit_time={};plans=[]
    api.start(["sumo","-n",str(net),"-r",str(route),"--seed",str(seed),"--step-length","1",
        "--route-steps","0","--time-to-teleport","-1","--max-depart-delay","-1",
        "--collision.action","warn","--pedestrian.model","striping","--no-step-log","true",
        "--duration-log.disable","true","--end",str(HORIZON)])
    try:
        actual=api.getVersion()[1];assert actual.split()[-1]==VERSION
        assert set(api.trafficlight.getIDList())=={m["j"] for m in meta}
        lanes=[f"a{i}_0" for i in range(n+1)]
        lengths=[api.lane.getLength(l) for l in lanes]
        caps=[max(1,math.floor(x/7.5)) for x in lengths]
        active=set();persons=set();road={};pos={};speed={}
        def vgroup(ph):return "A" if ph=="A" else "B" if ph in ("B","BP") else None
        for t in range(HORIZON):
            all_wait=set(requested)-set(admitted)
            blocked_at=[];signal_states=[]
            for i,m in enumerate(meta):
                s=states[i]
                a_ids=[k for k in active if road[k]==f"a{i}" and speed[k]<.1]
                b_ids=[k for k in active if road[k]==f"bi{i}" and speed[k]<.1]
                qa,qb=len(a_ids),len(b_ids);wa=max((waits[k] for k in a_ids),default=0);wb=max((waits[k] for k in b_ids),default=0)
                pids=[k for k in all_wait if planned[k][4]==i];oldest=min((requested[k] for k in pids),default=None)
                occupancy=sum(road[k]==f"a{i+1}" for k in active)
                blocked=i<n-1 and capacity_block(occupancy,caps[i+1],qa,policy=="adaptive_eta_storage")
                critical_now=i<n-1 and occupancy>=.85*caps[i+1]
                blocked_at.append(critical_now)
                in_transit=sum(road[k]==f"a{i}" and pos[k]<lengths[i]-20 and speed[k]>=.1 for k in active)
                cohorts[i]=[c for c in cohorts[i] if t<=c.expires]
                eta=upcoming(cohorts[i],t,in_transit) if i else 0
                def switch(target,reason):
                    nonlocal changes,vetoes
                    s.target=target;s.transition=t;changes+=1
                    vetoes+=int(reason=="storage_veto")
                    plans.append([t,i,s.phase,target,reason])
                if s.transition is None:
                    if s.phase in ("P","BP"):
                        if t-s.start>=10+m["clear"]:
                            if crossings[i]:extensions+=1
                            else:switch(("R" if m["mid"] else "B") if blocked else "A","clearance_complete")
                    else:
                        nxt,reason=choose(policy,m["mid"],s.phase,t-s.start,t,qa,qb,wa,wb,len(pids),oldest,eta,blocked,round(i*spacing/10))
                        eta_reviews+=int(reason=="eta")
                        if nxt!=s.phase:switch(nxt,reason)
                if s.transition is not None:
                    elapsed=t-s.transition
                    if elapsed>=5 and not internals[i] and not crossings[i]:
                        if s.target=="A" and blocked:
                            s.target="R" if m["mid"] else ("BP" if pids else "B")
                            vetoes+=1
                        s.phase=s.target;s.start=t;s.transition=None
                    else:
                        state="".join("y" if elapsed<3 and g==vgroup(s.phase) else "r" for _,g in sorted(m["groups"].items()))
                if s.transition is None:
                    state="".join("G" if (g==vgroup(s.phase) or (g=="P" and s.phase in ("P","BP") and t-s.start<10)) else "r"
                                  for _,g in sorted(m["groups"].items()))
                p_green=any(state[k]=="G" for k,g in m["groups"].items() if g=="P")
                a_open=any(state[k] in "Gy" for k,g in m["groups"].items() if g=="A")
                conflict+=int(a_open and (p_green or bool(crossings[i])))
                assert not(a_open and (p_green or crossings[i])),f"pedestrian conflict {i}/{t}"
                assert not(any(state[k] in "Gy" for k,g in m["groups"].items() if g=="B") and a_open)
                a_green=any(state[k]=="G" for k,g in m["groups"].items() if g=="A")
                green_ticks[i]+=int(a_green)
                critical_green+=int(critical_now and a_green)
                critical_yellow+=int(critical_now and a_open and not a_green)
                if m["mid"] and not pids and not crossings[i] and s.phase=="A" and s.transition is not None and not blocked:
                    # A request can have been observed at transition start; do not infer needless closure from later empty samples.
                    mid_empty_interruptions+=int(t==s.transition)
                api.trafficlight.setRedYellowGreenState(m["j"],state)
                assert api.trafficlight.getRedYellowGreenState(m["j"])==state
                signal_states.append((p_green,s.phase=="BP" and s.transition is None))
            scheduled.update(by_time[t])
            api.simulationStep()
            new=set(api.simulation.getDepartedIDList());exited=set(api.simulation.getArrivedIDList())
            pn=set(api.simulation.getDepartedPersonIDList());pf=set(api.simulation.getArrivedPersonIDList())
            assert not(new&entered or exited&done or pn&p_entered or pf&p_done)
            assert (new|pn)<=scheduled
            entered.update(new);done.update(exited);p_entered.update(pn);p_done.update(pf)
            for k in exited:exit_time[k]=t+1
            active=set(api.vehicle.getIDList());persons=set(api.person.getIDList())
            assert active==entered-done and persons==p_entered-p_done
            road={k:api.vehicle.getRoadID(k) for k in active}
            pos={k:api.vehicle.getLanePosition(k) for k in active}
            speed={k:api.vehicle.getSpeed(k) for k in active}
            p_roads={k:api.person.getRoadID(k) for k in persons}
            lane_ids={k:api.vehicle.getLaneID(k) for k in active}
            for i,m in enumerate(meta):
                internals[i]={k for k in active if lane_ids[k] in m["internal"]}
                before=crossings[i];crossings[i]={k for k in persons if p_roads[k]==m["crossing"]}
                completed.update(before-crossings[i])
                for k in crossings[i]-before:
                    assert k not in admitted
                    if k not in requested:requested[k]=t+1;unobserved+=1
                    admitted[k]=t+1;ped_wait[k]=t+1-requested[k]
                    pg,bp=signal_states[i];red_entries+=int(not pg);compatible+=int(bp)
                    assert pg,f"red pedestrian entry {i}/{t}"
                for k in persons-set(admitted):
                    if p_roads[k] in m["walkingareas"] and api.person.getNextEdge(k)==m["crossing"]:
                        requested.setdefault(k,t+1)
            assert p_done<=completed
            for i in range(1,n):
                present={k for k in active if road[k]==f"a{i}"}
                new_segment=present-segment_seen[i]
                segment_seen[i].update(present)
                if new_segment:
                    c=forecast(t+1,len(new_segment),max(1,lengths[i]-20))
                    cohorts[i].append(c)
                    for k in new_segment:issued[(i,k)]=c # synthetic evaluation only
                    critical_entries+=len(new_segment) if blocked_at[i-1] else 0
                for k in present:
                    if pos[k]>=lengths[i]-20 and (i,k) in issued:
                        arrived_eta.setdefault((i,k),t+1)
                excess=max(0,len(present)-.85*caps[i])
                critical+=excess;segment_critical[i]+=excess
            halted={k for k in active if speed[k]<.1}
            pending={k for k in scheduled-entered if planned[k][1]!="P"}
            for k in halted|pending:waits[k]+=1
            for k in active:
                if speed[k]>=.1:
                    moving.add(k);was_stopped.discard(k)
                elif k in moving and k not in was_stopped:
                    stops[k]+=1;was_stopped.add(k)
                overspeed+=int(speed[k]>VMAX+.1)
                if planned[k][1]=="A":speed_samples.append(speed[k])
            area_v+=len(halted)+len(pending);pending_ticks+=len(pending)
            corridor_area+=sum(planned[k][1]=="A" for k in halted|pending)
            transverse_area+=sum(planned[k][1]!="A" for k in halted|pending)
            area_p+=len(set(requested)-set(admitted))
            collisions+=api.simulation.getCollidingVehiclesNumber();teleports+=api.simulation.getStartingTeleportNumber()
        assert scheduled==set(planned)
        assert not any((collisions,teleports,overspeed,conflict,red_entries,mid_empty_interruptions))
        assert area_v==corridor_area+transverse_area and math.isclose(critical,sum(segment_critical))
        assert len(admitted)==len(completed)+sum(map(len,crossings))
        p_total=sum(r[1]=="P" for r in rows);v_total=len(rows)-p_total
        waiting=set(requested)-set(admitted)
        pw=list(ped_wait.values())+[HORIZON-requested[k] for k in waiting]
        corridor_done=[k for k in done if planned[k][1]=="A"]
        travel=[exit_time[k]-planned[k][0] for k in corridor_done]
        err=[abs(t-issued[k].nominal) for k,t in arrived_eta.items()]
        covered=sum(issued[k].earliest<=t<=issued[k].latest for k,t in arrived_eta.items())
        mean_speed=fmean(speed_samples) if speed_samples else None
        return {"runtime_version":actual,"vehicle_scheduled":v_total,"vehicle_exited":len(done),
            "vehicle_remaining":len(active),"vehicle_uninserted":v_total-len(entered),
            "corridor_scheduled":sum(r[1]=="A" for r in rows),"corridor_exited":len(corridor_done),
            "pedestrian_scheduled":p_total,"pedestrian_exited":len(p_done),"pedestrian_remaining":len(persons),
            "pedestrian_uninserted":p_total-len(p_entered),"pedestrian_completed":len(completed),
            "pedestrian_admitted":len(admitted),"pedestrian_crossing":sum(map(len,crossings)),"pedestrian_waiting":len(waiting),
            "pedestrian_unobserved_before_entry":unobserved,"vehicle_area":area_v,"pedestrian_area":area_p,
            "person_area":1.5*area_v+area_p,"pending_vehicle_seconds":pending_ticks,"critical_exposure":critical,
            "corridor_vehicle_area":corridor_area,"transverse_vehicle_area":transverse_area,
            "segment_critical_exposure":segment_critical[1:],
            "midblock_pedestrians_completed":sum(planned[k][4]==mid for k in completed) if mid is not None else None,
            "midblock_pedestrians_scheduled":sum(r[1]=="P" and r[4]==mid for r in rows) if mid is not None else None,
            "vehicle_max_wait":max(waits.values(),default=0),"pedestrian_max_wait":max(pw,default=0),
            "vehicle_p95_exited":percentile([waits[k] for k in done]),"pedestrian_p95_admitted":percentile(list(ped_wait.values())),
            "vehicle_deadline_violations":sum(v>VEH_LIMIT for v in waits.values()),
            "pedestrian_deadline_violations":sum(v>PED_LIMIT for v in pw),
            "mean_corridor_travel_seconds":fmean(travel) if travel else None,
            "mean_corridor_stops":fmean([stops[k] for k in corridor_done]) if travel else None,
            "no_stop_share":sum(stops[k]==0 for k in corridor_done)/len(travel) if travel else None,
            "mean_corridor_speed_mps":mean_speed,"corridor_speed_cv":pstdev(speed_samples)/mean_speed if mean_speed else None,
            "eta_issued":len(issued),"eta_arrived":len(arrived_eta),"eta_censored":len(issued)-len(arrived_eta),
            "eta_covered":covered,"eta_abs_error_sum":sum(err),"eta_mae_seconds":fmean(err) if err else None,
            "eta_coverage":covered/len(err) if err else None,"eta_reviews":eta_reviews,
            "phase_changes":changes,"storage_vetoes":vetoes,"critical_green_ticks":critical_green,
            "critical_yellow_ticks":critical_yellow,"critical_entries":critical_entries,
            "compatible_admissions":compatible,"extension_ticks":extensions,"green_ticks":green_ticks,
            "mid_empty_interruptions":mid_empty_interruptions,"collisions":collisions,"teleports":teleports,
            "overspeed_samples":overspeed,"conflict_violations":conflict,"red_entries":red_entries,"plans":plans}
    finally:api.close()


def case(api,root,family,seed,policies=POLICIES):
    net,meta=network(root,family)
    rows=demand(family,seed);route=root/"demand.rou.xml";routes(route,meta,rows)
    return {"family":family,"nodes":len(meta),"seed":seed,"conflicts_verified":True,
        "network_sha256":hashlib.sha256(ET.canonicalize(from_file=net,with_comments=False).encode()).hexdigest(),
        "demand_sha256":sha256_file(route),"metrics":{p:trajectory(api,net,meta,route,rows,family,seed,p) for p in policies}}


FIELDS=("person_area","vehicle_area","corridor_vehicle_area","transverse_vehicle_area","pedestrian_area","critical_exposure","vehicle_exited","corridor_exited",
    "pedestrian_completed","vehicle_uninserted","pending_vehicle_seconds","vehicle_max_wait","pedestrian_max_wait",
    "mean_corridor_travel_seconds","mean_corridor_stops","no_stop_share","mean_corridor_speed_mps","corridor_speed_cv",
    "phase_changes","storage_vetoes","critical_green_ticks","critical_yellow_ticks","critical_entries","compatible_admissions",
    "extension_ticks","eta_reviews","eta_issued","eta_arrived","eta_censored","pedestrian_admitted","pedestrian_waiting")


def summary(rows):
    out={}
    for p in POLICIES:
        ms=[r["metrics"][p] for r in rows];d={}
        for k in FIELDS:
            vals=[m[k] for m in ms if m[k] is not None]
            d[k]=fmean(vals) if vals else None
            if len(vals)!=len(ms):d[k+"_cases"]=len(vals)
        for k in ("vehicle_max_wait","pedestrian_max_wait"):d["worst_"+k]=max(m[k] for m in ms)
        for k in ("vehicle_deadline_violations","pedestrian_deadline_violations","collisions","teleports",
                  "overspeed_samples","conflict_violations","red_entries","eta_arrived","eta_issued","eta_censored",
                  "eta_covered","eta_abs_error_sum","pedestrian_completed","pedestrian_scheduled","corridor_scheduled",
                  "corridor_exited","vehicle_scheduled"):
            d["total_"+k]=sum(m[k] for m in ms)
        d["eta_coverage"]=d["total_eta_covered"]/d["total_eta_arrived"] if d["total_eta_arrived"] else None
        d["eta_mae_seconds"]=d["total_eta_abs_error_sum"]/d["total_eta_arrived"] if d["total_eta_arrived"] else None
        d["occupancy_sensitivity"]={str(o):o*d["vehicle_area"]+d["pedestrian_area"] for o in (1,1.5,2)}
        out[p]=d
    return out


def gate(s,candidate):
    c=s[candidate];checks={}
    def le(a,b,factor):
        return a is not None and b is not None and a<=factor*b
    for ref in POLICIES[:2]:
        b=s[ref]
        checks[ref]={**{k:le(c[k],b[k],1.05) for k in ("person_area","vehicle_area","pedestrian_area","critical_exposure",
            "worst_vehicle_max_wait","worst_pedestrian_max_wait","mean_corridor_stops","mean_corridor_travel_seconds","corridor_speed_cv")},
            **{k:c[k]>=.95*b[k] for k in ("vehicle_exited","corridor_exited","pedestrian_completed")},
            **{k:c[k]<=b[k] for k in ("total_vehicle_deadline_violations","total_pedestrian_deadline_violations","vehicle_uninserted")}}
    checks["eta"]={"coverage":c["eta_coverage"] is not None and c["eta_coverage"]>=.7,
                   "error_measured":c["eta_mae_seconds"] is not None}
    return {"passed":all(v for group in checks.values() for v in group.values()),"checks":checks}


def run():
    api=ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-d-") as d:
        rows=[case(api,Path(d)/f"{f}-{s}",f,s) for f in FAMILIES for s in SEEDS]
    subsets={"overall":rows,"two":[r for r in rows if r["nodes"]==2],"three":[r for r in rows if r["nodes"]==3],
             "stress":[r for r in rows if r["family"] in ("two_compact","three_storage")]}
    summaries={k:summary(v) for k,v in subsets.items()}
    families={f:summary([r for r in rows if r["family"]==f]) for f in FAMILIES}
    gates={}
    for p in POLICIES[2:]:
        g={k:gate(summaries[k],p) for k in ("two","three","stress")}
        g["improvement_vs_independent"]=summaries["overall"][p]["person_area"]<summaries["overall"]["independent"]["person_area"]
        g["passed"]=g["improvement_vs_independent"] and all(g[k]["passed"] for k in ("two","three","stress"))
        gates[p]=g
    report={"scope":"pimcat_d_corridor_synthetic_not_field","sumo_version":VERSION,
        "sumo_validation":"EXECUTED_SYNTHETIC","cases":len(rows),"trajectories":len(rows)*len(POLICIES),
        "horizon_seconds":HORIZON,"seeds":list(SEEDS),"policies":list(POLICIES),"summaries":summaries,
        "families":families,"gates":gates,"rows":rows,"research_gate_passed":gates["adaptive_eta_storage"]["passed"],
        "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","field_speed_calibration":"NOT_RUN",
        "candidate_promoted":False,"operationally_validated":False,"physical_actuation":False,
        "commercial_demo_authorized":False,"operational_decision":"abstain"}
    report["result_sha256"]=fingerprint(report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    output=Path(a.output)
    if output.exists():raise ValueError("no evidence overwrite")
    report=run()
    with output.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)


if __name__=="__main__":main()
