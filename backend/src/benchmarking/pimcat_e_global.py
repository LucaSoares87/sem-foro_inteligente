"""PIMCAT E: offline directed grid twin, global pressure and microscopic research."""
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
from statistics import fmean,pstdev
from src.archive.store import fingerprint
from src.benchmarking.si11d_sumo import ensure_version,write_xml,VERSION
from src.benchmarking.pimcat_d_sumo import capacity_block,State,percentile,VMAX
from src.benchmarking.pimcat_local import PED_LIMIT,VEH_LIMIT
from src.benchmarking.pimcat_midblock import assess
from src.validation.io import sha256_file

HORIZON=600
SEEDS=tuple(range(9100,9104))
POLICIES=("local_demand","local_pressure","global_pressure","global_storage")
# columns,spacing,east/north/ped rates,pattern,midblock
FAMILIES={
 "balanced":(2,220,.18,.18,.05,"steady",False),
 "burst":(3,220,.25,.19,.07,"burst",False),
 "compact":(2,100,.38,.33,.09,"steady",False),
 "deadlines":(3,100,.48,.42,.15,"slow",False),
 "rp07_single":(2,220,.20,.18,.06,"single",True),
 "outage":(3,100,.32,.28,.10,"burst",True),
}
COLORS={"free":"#16a34a","moderate":"#eab308","intense":"#f97316","critical":"#dc2626","unknown":"#94a3b8"}


@dataclass(frozen=True)
class Reading:
    tick:int
    count:int
    queue:int
    capacity:int
    speed:float


def criticity(reading,now,available=True):
    if not available or reading is None:return None,"unknown"
    r=reading
    if (type(now) is not int or type(r.tick) is not int or not 0<=now-r.tick<=5 or
        any(type(x) is not int for x in (r.count,r.queue,r.capacity)) or
        not 0<=r.queue<=r.count or r.capacity<=0 or not math.isfinite(r.speed) or not 0<=r.speed<=VMAX+.1):
        return None,"unknown"
    v=0. if not r.count else max(0.,min(1.,.5*r.count/r.capacity+.3*r.queue/r.capacity+.2*(1-r.speed/VMAX)))
    return v,"free" if v<.25 else "moderate" if v<.5 else "intense" if v<.75 else "critical"


def central_available(family,t):
    return not(family=="outage" and (180<=t<300 or 420<=t<480))


def pressure(a,b):
    return a.queue/a.capacity-b.count/b.capacity


def network_context(graph,readings,j,t,available):
    """Graph-derived one-hop extension beyond local approach/destination.
    All referenced observations must be current; no imputation of missing edges.
    """
    if not available:return None
    moves=graph["movements"]
    result={}
    for g,(origin,dest) in moves[j].items():
        before=[a for ms in moves.values() for a,b in ms.values() if b==origin]
        after=[b for ms in moves.values() for a,b in ms.values() if a==dest]
        keys=[origin,*before,*after]
        values={k:criticity(readings.get(k),t)[0] for k in keys}
        if any(v is None for v in values.values()):return None
        result[g]=.5*values[origin]+.25*max((values[k] for k in before),default=0)-.25*max((values[k] for k in after),default=0)
    return result


def arbitrate(policy,mid,phase,age,t,local,central,p,oldest,waits):
    """Pure simulation preference. local measurements include independent destination sensor."""
    assert policy in POLICIES
    if phase in ("A","B") and age<12:return phase,"P0_minimum"
    if phase!="R" and t%5:return phase,"P0_review"
    effective=policy if central is not None or not policy.startswith("global") else "local_pressure"
    groups=("A",) if mid else ("A","B")
    blocked={g:capacity_block(local[g][1].count,local[g][1].capacity,local[g][0].queue,effective=="global_storage") for g in groups}
    allowed=[g for g in groups if not blocked[g]]
    if mid:
        rp=assess(now=t,waiting="demand" if p else "empty",crossing="clear",phase="vehicle",topology_confirmed=True,
            clearance_complete=True,oldest_request=oldest,other_obligation=blocked["A"])
        assert rp.operational_decision=="abstain" and not rp.physical_actuation
        if rp.preference_in_simulation=="hold_vehicle_preference":return "A","P6_rp07"
    def ped():return "BP" if "B" in allowed else "P"
    pa=t-oldest if oldest is not None else -1
    urgent=[g for g in allowed if waits[g]>=VEH_LIMIT-20]
    if p and pa>=PED_LIMIT-20 and (not urgent or PED_LIMIT-pa<=min(VEH_LIMIT-waits[g] for g in urgent)):
        return ped(),"P2_ped_deadline"
    if urgent:
        g=max(urgent,key=lambda g:(waits[g],g==phase))
        return ("BP" if g=="B" and p else g),"P2_vehicle_deadline"
    if not allowed:return ("P" if p else "R"),"P3_storage"
    if mid:
        if p and (not local["A"][0].queue or p>=1.5*local["A"][0].queue):return "P","P5_request"
        return "A","P6_rp07_wait"
    def score(g):
        a,b=local[g]
        if effective=="local_demand":return a.queue
        s=pressure(a,b)
        if effective.startswith("global"):
            s+=central[g]
        return s
    # Do not select an empty movement over actual demand just because destination is empty.
    demand_groups=[g for g in allowed if local[g][0].count]
    g=max(demand_groups or allowed,key=lambda g:(score(g),g==phase,g=="A"))
    if p and (g=="B" or not local["A"][0].count):return ped(),"P5_compatible"
    return g,"P4_global" if effective.startswith("global") else "P5_local"


def network(root,family):
    cols,spacing,_,_,_,_,mid=FAMILIES[family]
    root.mkdir(parents=True,exist_ok=True)
    nodes=ET.Element("nodes");edges=ET.Element("edges");cons=ET.Element("connections")
    coordinates={};edge_map={};movements={};route_map={}
    def node(k,x,y,kind="priority"):
        coordinates[k]=(x,y)
        ET.SubElement(nodes,"node",id=k,x=str(x),y=str(y),type=kind)
    def edge(k,f,t,ped=False):
        attrs={"from":f,"to":t,"numLanes":"1","speed":"5" if ped else str(VMAX)}
        attrs.update({"allow":"pedestrian","width":"3","spreadType":"center"} if ped else {"disallow":"pedestrian"})
        ET.SubElement(edges,"edge",id=k,attrib=attrs)
        if not ped:edge_map[k]=(f,t)
    def connect(a,b):
        ET.SubElement(cons,"connection",attrib={"from":a,"to":b,"fromLane":"0","toLane":"0"})
    for y in range(2):
        for x in range(cols):
            j=f"J{x}_{y}";node(j,x*spacing,y*spacing,"traffic_light");movements[j]={}
    if mid:node("M",spacing/2,0,"traffic_light");movements["M"]={}
    for y in range(2):
        w=f"W{y}";e=f"E{y}"
        node(w,-180,y*spacing);node(e,(cols-1)*spacing+180,y*spacing)
        chain=[w]+[f"J{x}_{y}" for x in range(cols)]+[e]
        if mid and y==0:chain.insert(2,"M")
        names=[]
        for i,(f,t) in enumerate(zip(chain,chain[1:])):
            name=f"a{y}_{i}";edge(name,f,t);names.append(name)
        route_map[f"A{y}"]=names
        for i,j in enumerate(chain[1:-1]):
            connect(names[i],names[i+1]);movements[j]["A"]=(names[i],names[i+1])
    for x in range(cols):
        s=f"S{x}";n=f"N{x}";node(s,x*spacing,-180);node(n,x*spacing,spacing+180)
        chain=[s,f"J{x}_0",f"J{x}_1",n];names=[]
        for i,(f,t) in enumerate(zip(chain,chain[1:])):
            name=f"b{x}_{i}";edge(name,f,t);names.append(name)
        route_map[f"B{x}"]=names
        for i,j in enumerate(chain[1:-1]):
            connect(names[i],names[i+1]);movements[j]["B"]=(names[i],names[i+1])
    for j,m in movements.items():
        x,y=coordinates[j];px=x if j=="M" else x+35
        node("PS"+j,px,y-35);node("PN"+j,px,y+35)
        edge("pi"+j,"PS"+j,j,True);edge("po"+j,j,"PN"+j,True)
        ET.SubElement(cons,"crossing",node=j,edges=m["A"][1],width="4")
    for name,tree in (("nodes",nodes),("edges",edges),("connections",cons)):write_xml(root/(name+".xml"),tree)
    exe=shutil.which("netconvert")
    if not exe:raise RuntimeError("netconvert missing")
    net=root/"network.net.xml"
    p=subprocess.run([exe,"--node-files",str(root/"nodes.xml"),"--edge-files",str(root/"edges.xml"),
        "--connection-files",str(root/"connections.xml"),"--no-turnarounds","true","--output-file",str(net)],
        capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr)
    tree=ET.parse(net).getroot();meta={}
    for j,ms in movements.items():
        junction=tree.find(f"./junction[@id='{j}']")
        internal=junction.get("intLanes").split()
        requests={int(q.get("index")):q.get("foes") for q in junction.findall("request")}
        crossings=[e for e in tree.findall("edge") if e.get("function")=="crossing" and e.get("id").startswith(":"+j+"_")]
        assert len(crossings)==1,f"crossing {j}"
        crossing=crossings[0].get("id");clane=crossings[0].find("lane");ci=internal.index(clane.get("id"))
        groups={};links={}
        for g,(a,b) in ms.items():
            c=tree.find(f"./connection[@from='{a}'][@to='{b}']")
            assert c is not None and c.get("tl")==j
            k=int(c.get("linkIndex"));assert k not in groups
            groups[k]=g;links[k]=internal.index(c.get("via"))
        pc=[c for c in tree.findall("connection") if c.get("tl")==j and c.get("to")==crossing]
        assert pc
        for c in pc:
            k=int(c.get("linkIndex"));assert k not in groups
            groups[k]="P";links[k]=ci
        assert set(groups)==set(range(len(tree.find(f"./tlLogic[@id='{j}']/phase").get("state"))))
        for k,g in groups.items():
            for l,h in groups.items():
                if k>=l:continue
                a,b=links[k],links[l]
                foe=requests[a][-1-b]=="1" or requests[b][-1-a]=="1"
                assert foe==({g,h} in ({"A","B"},{"A","P"})),f"foe {j} {g}/{h}"
        meta[j]={"groups":groups,"movements":ms,"internal":internal,"crossing":crossing,
            "walkingareas":[e.get("id") for e in tree.findall("edge") if e.get("function")=="walkingarea" and e.get("id").startswith(":"+j+"_")],
            "pi_length":float(tree.find(f"./edge[@id='pi{j}']/lane").get("length")),
            "clear":math.ceil(1+float(clane.get("length"))/.6)+1}
    graph={"nodes":{k:{"x":v[0],"y":v[1],"kind":"midblock" if k=="M" else "intersection" if k in meta else "boundary"} for k,v in coordinates.items() if not k.startswith(("PS","PN"))},
           "edges":{k:{"from":v[0],"to":v[1],"length_m":float(tree.find(f"./edge[@id='{k}']/lane").get("length"))} for k,v in edge_map.items()},
           "movements":movements,"routes":route_map,"origin":"synthetic"}
    for k,e in graph["edges"].items():e["capacity_proxy"]=max(1,math.floor(e["length_m"]/7.5))
    return net,meta,graph


def demand(family,seed,meta,graph):
    _,_,a,b,p,pattern,_=FAMILIES[family];rng=Random(seed);rows=[]
    for t in range(HORIZON):
        for r in sorted(graph["routes"]):
            rate=(a if r.startswith("A") else b)*(1.8 if pattern=="burst" and t%90<40 else .2 if pattern=="burst" else 1)
            if rng.random()<min(1,rate):rows.append((t,r,f"v{t}_{r}",0,None))
        for j in sorted(meta):
            if (pattern=="single" and j=="M" and t==110) or (not(pattern=="single" and j=="M") and rng.random()<p):
                speed=.4 if pattern=="slow" and rng.random()<.3 else (.9 if rng.random()<.5 else 1.2)
                rows.append((t,"P",f"p{t}_{j}",speed,j))
    return rows


def routes(path,meta,graph,rows):
    root=ET.Element("routes")
    ET.SubElement(root,"vType",id="car",length="5",minGap="2.5",sigma="0",speedFactor="1",speedDev="0",maxSpeed=str(VMAX))
    ET.SubElement(root,"vType",id="walker",vClass="pedestrian",speedFactor="1",speedDev="0",maxSpeed="1.2")
    for r,edges in graph["routes"].items():ET.SubElement(root,"route",id=r,edges=" ".join(edges))
    for t,r,k,speed,j in rows:
        if r=="P":
            person=ET.SubElement(root,"person",id=k,type="walker",depart=str(t),departPos=str(max(0,meta[j]["pi_length"]-3)))
            ET.SubElement(person,"walk",edges=f"pi{j} po{j}",speed=str(speed),arrivalPos="3")
        else:ET.SubElement(root,"vehicle",id=k,type="car",route=r,depart=str(t),departSpeed="0")
    write_xml(path,root)


def snapshot(graph,readings,t,available):
    out={}
    for k,e in graph["edges"].items():
        r=readings.get(k);val,level=criticity(r,t,available)
        out[k]={"index":val,"level":level,"count":r.count if val is not None else None,
            "queue":r.queue if val is not None else None,"speed_mps":r.speed if val is not None else None}
    return {"tick":t,"central_available":available,"origin":"synthetic","edges":out}


def render_svg(graph,snap,path):
    root=ET.Element("svg",xmlns="http://www.w3.org/2000/svg",viewBox="0 0 920 550")
    ET.SubElement(root,"rect",width="920",height="550",fill="#f8fafc")
    coords=graph["nodes"];xs=[n["x"] for n in coords.values()];ys=[n["y"] for n in coords.values()]
    def xy(k):
        n=coords[k];return 70+780*(n["x"]-min(xs))/(max(xs)-min(xs)),430-350*(n["y"]-min(ys))/(max(ys)-min(ys))
    def label(x,y,value,size=13,color="#0f172a"):
        ET.SubElement(root,"text",x=str(x),y=str(y),fill=color,attrib={"font-size":str(size),"font-family":"sans-serif"}).text=value
    label(30,30,f"PIMCAT E | SIMULACAO - t={snap['tick']}s | central {'online' if snap['central_available'] else 'indisponivel'}",19)
    for k,e in graph["edges"].items():
        x,y=xy(e["from"]);u,v=xy(e["to"]);color=COLORS[snap["edges"][k]["level"]]
        ET.SubElement(root,"line",x1=str(x),y1=str(y),x2=str(u),y2=str(v),stroke=color,attrib={"stroke-width":"9","stroke-linecap":"round"})
        dx,dy=u-x,v-y;length=math.hypot(dx,dy);ax,ay=x+dx*.66,y+dy*.66
        ux,uy=dx/length,dy/length
        points=[(ax,ay),(ax-10*ux-5*uy,ay-10*uy+5*ux),(ax-10*ux+5*uy,ay-10*uy-5*ux)]
        ET.SubElement(root,"polygon",points=" ".join(f"{a},{b}" for a,b in points),fill="#334155")
    for k,n in coords.items():
        x,y=xy(k)
        ET.SubElement(root,"circle",cx=str(x),cy=str(y),r="7",fill="#fff",stroke="#334155",attrib={"stroke-width":"2"})
        label(x+10,y-10,k+(" RP07" if n["kind"]=="midblock" else ""),11)
    for i,(level,color) in enumerate(COLORS.items()):
        x=30+i*175;ET.SubElement(root,"rect",x=str(x),y="478",width="18",height="14",fill=color)
        label(x+24,490,level)
    label(30,525,"Rede sintetica; indice experimental; sem autorizacao de campo.",12)
    write_xml(path,root)


def trajectory(api,net,meta,graph,route,rows,family,seed,policy,*,context_fn=network_context,snapshot_ticks=()):
    states={j:State() for j in meta}
    planned={r[2]:r for r in rows};by_time=defaultdict(set)
    for r in rows:by_time[r[0]].add(r[2])
    scheduled=set();entered=set();done=set();p_entered=set();p_done=set()
    requested={};admitted={};completed=set();ped_wait={};waits=defaultdict(int)
    moving=set();was_stopped=set();stops=defaultdict(int);exit_time={}
    crossings={j:set() for j in meta};internals={j:set() for j in meta}
    active=set();persons=set();road={};speed={}
    area_v=area_p=critical=0.;critical_duration=defaultdict(int)
    edge_critical=defaultdict(float);critical_entries=critical_open=0
    changes=extensions=vetoes=0;fallback_ticks=global_reviews=0
    collisions=teleports=overspeed=red_entries=conflicts=0
    rp07_empty=compatible=unobserved=0
    speed_samples=[];plans=[];snapshots=[]
    internal_edges={k for k,e in graph["edges"].items() if e["from"] in meta and e["to"] in meta}
    # Track only synthetic IDs for accounting; no identity in policy input.
    previous_edges={k:set() for k in graph["edges"]}
    bp_yellow={}
    api.start(["sumo","-n",str(net),"-r",str(route),"--seed",str(seed),"--step-length","1",
        "--route-steps","0","--time-to-teleport","-1","--max-depart-delay","-1",
        "--collision.action","warn","--pedestrian.model","striping","--no-step-log","true",
        "--duration-log.disable","true","--end",str(HORIZON)])
    try:
        actual=api.getVersion()[1];assert actual.split()[-1]==VERSION
        assert set(api.trafficlight.getIDList())==set(meta)
        caps={k:e["capacity_proxy"] for k,e in graph["edges"].items()}
        assert all(caps[k]==max(1,math.floor(api.lane.getLength(k+"_0")/7.5)) for k in caps)
        def vgroup(ph):return "A" if ph=="A" else "B" if ph in ("B","BP") else None
        for t in range(HORIZON):
            available=central_available(family,t)
            fallback_ticks+=int(policy.startswith("global") and not available)
            edge_ids={k:set() for k in caps}
            for k in active:
                if road[k] in edge_ids:edge_ids[road[k]].add(k)
            readings={k:Reading(t,len(ids),sum(speed[v]<.1 for v in ids),caps[k],fmean([speed[v] for v in ids]) if ids else 0.) for k,ids in edge_ids.items()}
            if (family=="outage" and seed==9100 and policy=="global_storage" and t in (175,240,305)) or t in snapshot_ticks:
                snapshots.append(snapshot(graph,readings,t,available))
            all_wait=set(requested)-set(admitted);signal_states={}
            blocked_edges={k for k in internal_edges if readings[k].count>=.85*caps[k]}
            for j,m in meta.items():
                s=states[j];mid=j=="M";ms=m["movements"]
                local={g:(readings[a],readings[b]) for g,(a,b) in ms.items()}
                central=context_fn(graph,readings,j,t,available)
                pids=[k for k in all_wait if planned[k][4]==j];oldest=min((requested[k] for k in pids),default=None)
                ages={g:max((waits[k] for k in edge_ids[a] if speed[k]<.1),default=0) for g,(a,b) in ms.items()}
                anticipate=policy=="global_storage" and available
                blocked={g:capacity_block(b.count,b.capacity,a.queue,anticipate) for g,(a,b) in local.items()}
                def switch(target,reason):
                    nonlocal changes,vetoes,rp07_empty,global_reviews
                    if mid and s.phase=="A" and not pids and not crossings[j] and not blocked["A"]:rp07_empty+=1
                    s.target=target;s.transition=t;changes+=1
                    vetoes+=int(reason=="P3_storage")
                    plans.append([t,j,s.phase,target,reason])
                def choice(ph,age):
                    nonlocal global_reviews
                    target,reason=arbitrate(policy,mid,ph,age,t,local,central,len(pids),oldest,ages)
                    global_reviews+=int(reason=="P4_global")
                    assert available or reason!="P4_global"
                    return target,reason
                if s.transition is None:
                    if s.phase in ("P","BP"):
                        if s.phase=="BP" and blocked.get("B") and t-s.start>=12:bp_yellow.setdefault(j,t)
                        if t-s.start>=10+m["clear"]:
                            if crossings[j]:extensions+=1
                            elif j in bp_yellow and t-bp_yellow[j]<3:pass
                            else:
                                target,reason=choice("R",0)
                                switch(target,"clearance_"+reason)
                    else:
                        target,reason=choice(s.phase,t-s.start)
                        if target!=s.phase:switch(target,reason)
                if s.transition is not None:
                    elapsed=t-s.transition
                    if elapsed>=5 and not internals[j] and not crossings[j]:
                        g=vgroup(s.target)
                        if g is not None and blocked[g]:
                            s.target="P" if pids else "R";vetoes+=1
                        assert vgroup(s.target) is None or not blocked[vgroup(s.target)]
                        s.phase=s.target;s.start=t;s.transition=None;bp_yellow.pop(j,None)
                    else:
                        state="".join("y" if elapsed<3 and g==vgroup(s.phase) and j not in bp_yellow else "r" for _,g in sorted(m["groups"].items()))
                if s.transition is None:
                    state="".join(("y" if t-bp_yellow[j]<3 else "r") if g=="B" and s.phase=="BP" and j in bp_yellow else
                        "G" if g==vgroup(s.phase) or (g=="P" and s.phase in ("P","BP") and t-s.start<10) else "r"
                        for _,g in sorted(m["groups"].items()))
                pg=any(state[k]=="G" for k,g in m["groups"].items() if g=="P")
                ao=any(state[k] in "Gy" for k,g in m["groups"].items() if g=="A")
                bo=any(state[k] in "Gy" for k,g in m["groups"].items() if g=="B")
                conflicts+=int(ao and (pg or bool(crossings[j]) or bo))
                assert not(ao and (pg or crossings[j] or bo)),f"conflict {j}/{t}"
                for g,(_,dest) in ms.items():
                    if dest in blocked_edges and any(state[k] in "Gy" for k,h in m["groups"].items() if h==g):critical_open+=1
                api.trafficlight.setRedYellowGreenState(j,state)
                assert api.trafficlight.getRedYellowGreenState(j)==state
                signal_states[j]=(pg,bo and pg)
            scheduled.update(by_time[t]);api.simulationStep()
            new=set(api.simulation.getDepartedIDList());exited=set(api.simulation.getArrivedIDList())
            pn=set(api.simulation.getDepartedPersonIDList());pf=set(api.simulation.getArrivedPersonIDList())
            assert not(new&entered or exited&done or pn&p_entered or pf&p_done)
            assert (new|pn)<=scheduled
            entered.update(new);done.update(exited);p_entered.update(pn);p_done.update(pf)
            for k in exited:exit_time[k]=t+1
            active=set(api.vehicle.getIDList());persons=set(api.person.getIDList())
            assert active==entered-done and persons==p_entered-p_done
            road={k:api.vehicle.getRoadID(k) for k in active};speed={k:api.vehicle.getSpeed(k) for k in active}
            lane={k:api.vehicle.getLaneID(k) for k in active};proad={k:api.person.getRoadID(k) for k in persons}
            for j,m in meta.items():
                internals[j]={k for k in active if lane[k] in m["internal"]}
                before=crossings[j];crossings[j]={k for k in persons if proad[k]==m["crossing"]}
                completed.update(before-crossings[j])
                for k in crossings[j]-before:
                    assert k not in admitted
                    if k not in requested:requested[k]=t+1;unobserved+=1
                    admitted[k]=t+1;ped_wait[k]=t+1-requested[k]
                    pg,bp=signal_states[j];red_entries+=int(not pg);compatible+=int(bp)
                    assert pg,f"red entry {j}/{t}"
                for k in persons-set(admitted):
                    if proad[k] in m["walkingareas"] and api.person.getNextEdge(k)==m["crossing"]:requested.setdefault(k,t+1)
            assert p_done<=completed
            now_edges={k:set() for k in caps}
            for k in active:
                if road[k] in now_edges:now_edges[road[k]].add(k)
            for k in sorted(internal_edges):
                excess=max(0,len(now_edges[k])-.85*caps[k]);critical+=excess;edge_critical[k]+=excess
                critical_duration[k]+=int(excess>0)
                if k in blocked_edges:critical_entries+=len(now_edges[k]-previous_edges[k])
            previous_edges=now_edges
            halted={k for k in active if speed[k]<.1};pending={k for k in scheduled-entered if planned[k][1]!="P"}
            for k in halted|pending:waits[k]+=1
            for k in active:
                if speed[k]>=.1:moving.add(k);was_stopped.discard(k)
                elif k in moving and k not in was_stopped:stops[k]+=1;was_stopped.add(k)
                overspeed+=int(speed[k]>VMAX+.1);speed_samples.append(speed[k])
            area_v+=len(halted)+len(pending);area_p+=len(set(requested)-set(admitted))
            collisions+=api.simulation.getCollidingVehiclesNumber();teleports+=api.simulation.getStartingTeleportNumber()
        assert scheduled==set(planned)
        assert not any((collisions,teleports,overspeed,conflicts,red_entries,rp07_empty))
        assert len(admitted)==len(completed)+sum(map(len,crossings.values()))
        assert math.isclose(critical,sum(edge_critical.values()),abs_tol=1e-7)
        if family=="rp07_single":
            assert sum(planned[k][4]=="M" for k in completed)==1
            assert all(v<=PED_LIMIT for k,v in ped_wait.items() if planned[k][4]=="M")
        p_total=sum(r[1]=="P" for r in rows);v_total=len(rows)-p_total
        waiting=set(requested)-set(admitted);pw=list(ped_wait.values())+[HORIZON-requested[k] for k in waiting]
        travel=[exit_time[k]-planned[k][0] for k in done];mean_speed=fmean(speed_samples) if speed_samples else None
        assert fallback_ticks==(180 if family=="outage" and policy.startswith("global") else 0)
        return {"runtime_version":actual,"vehicle_scheduled":v_total,"vehicle_exited":len(done),"vehicle_remaining":len(active),"vehicle_uninserted":v_total-len(entered),
            "pedestrian_scheduled":p_total,"pedestrian_exited":len(p_done),"pedestrian_remaining":len(persons),"pedestrian_uninserted":p_total-len(p_entered),
            "pedestrian_admitted":len(admitted),"pedestrian_completed":len(completed),"pedestrian_crossing":sum(map(len,crossings.values())),"pedestrian_waiting":len(waiting),
            "pedestrian_unobserved_before_entry":unobserved,"vehicle_area":area_v,"pedestrian_area":area_p,"person_area":1.5*area_v+area_p,
            "vehicle_max_wait":max(waits.values(),default=0),"pedestrian_max_wait":max(pw,default=0),
            "vehicle_p95_exited":percentile([waits[k] for k in done]),"pedestrian_p95_admitted":percentile(list(ped_wait.values())),
            "vehicle_deadline_violations":sum(w>VEH_LIMIT for w in waits.values()),"pedestrian_deadline_violations":sum(w>PED_LIMIT for w in pw),
            "mean_travel_seconds":fmean(travel) if travel else None,"mean_stops":fmean([stops[k] for k in done]) if done else None,
            "speed_cv":pstdev(speed_samples)/mean_speed if mean_speed else None,"mean_speed_mps":mean_speed,
            "critical_exposure":critical,"critical_entries":critical_entries,"critical_open_ticks":critical_open,
            "edge_critical_exposure":dict(edge_critical),"edge_critical_duration":dict(critical_duration),
            "fallback_ticks":fallback_ticks,"global_reviews":global_reviews,"phase_changes":changes,"storage_vetoes":vetoes,"extension_ticks":extensions,
            "compatible_admissions":compatible,"rp07_empty_interruptions":rp07_empty,"midblock_completed":sum(planned[k][4]=="M" for k in completed),
            "collisions":collisions,"teleports":teleports,"overspeed_samples":overspeed,"conflict_violations":conflicts,"red_entries":red_entries,
            "plans":plans,"snapshots":snapshots}
    finally:api.close()


def case(api,root,family,seed,policies=POLICIES,*,context_fn=network_context,snapshot_ticks=()):
    net,meta,graph=network(root,family);rows=demand(family,seed,meta,graph)
    route=root/"demand.rou.xml";routes(route,meta,graph,rows)
    return {"family":family,"columns":FAMILIES[family][0],"seed":seed,"nodes":len(meta),"conflicts_verified":True,
            "graph":graph,"network_sha256":hashlib.sha256(ET.canonicalize(from_file=net,with_comments=False).encode()).hexdigest(),
            "demand_sha256":sha256_file(route),"metrics":{p:trajectory(api,net,meta,graph,route,rows,family,seed,p,context_fn=context_fn,snapshot_ticks=snapshot_ticks) for p in policies}}


FIELDS=("person_area","vehicle_area","pedestrian_area","vehicle_exited","vehicle_uninserted","pedestrian_completed",
    "vehicle_max_wait","pedestrian_max_wait","mean_travel_seconds","mean_stops","speed_cv","mean_speed_mps","critical_exposure",
    "critical_entries","critical_open_ticks","phase_changes","storage_vetoes","extension_ticks","fallback_ticks","global_reviews","compatible_admissions")
def summary(rows,policies=POLICIES):
    out={}
    for p in policies:
        ms=[r["metrics"][p] for r in rows];d={}
        for k in FIELDS:
            vals=[m[k] for m in ms if m[k] is not None];d[k]=fmean(vals) if vals else None
            if len(vals)!=len(ms):d[k+"_cases"]=len(vals)
        for k in ("vehicle_max_wait","pedestrian_max_wait"):d["worst_"+k]=max(m[k] for m in ms)
        for k in ("vehicle_deadline_violations","pedestrian_deadline_violations","vehicle_scheduled","pedestrian_scheduled",
            "vehicle_exited","pedestrian_completed","critical_entries","fallback_ticks","collisions","teleports","overspeed_samples",
            "conflict_violations","red_entries","rp07_empty_interruptions","midblock_completed"):
            d["total_"+k]=sum(m[k] for m in ms)
        d["occupancy_sensitivity"]={str(o):o*d["vehicle_area"]+d["pedestrian_area"] for o in (1,1.5,2)}
        out[p]=d
    return out


def gate(s,candidate):
    c=s[candidate];checks={}
    for ref in POLICIES[:2]:
        b=s[ref]
        checks[ref]={**{k:c[k] is not None and b[k] is not None and c[k]<=1.05*b[k] for k in ("person_area","vehicle_area","pedestrian_area","worst_vehicle_max_wait","worst_pedestrian_max_wait","critical_exposure","critical_entries","mean_travel_seconds","mean_stops","speed_cv")},
            **{k:c[k]>=.95*b[k] for k in ("vehicle_exited","pedestrian_completed")},
            **{k:c[k]<=b[k] for k in ("total_vehicle_deadline_violations","total_pedestrian_deadline_violations","vehicle_uninserted")}}
    return {"passed":all(v for group in checks.values() for v in group.values()),"checks":checks}


def run():
    api=ensure_version()
    with tempfile.TemporaryDirectory(prefix="pimcat-e-") as d:
        rows=[case(api,Path(d)/f"{f}-{s}",f,s) for f in FAMILIES for s in SEEDS]
    subsets={"overall":rows,"two_columns":[r for r in rows if r["columns"]==2],"three_columns":[r for r in rows if r["columns"]==3],
        "stress":[r for r in rows if r["family"] in ("compact","deadlines","outage")]}
    summaries={k:summary(v) for k,v in subsets.items()}
    families={f:summary([r for r in rows if r["family"]==f]) for f in FAMILIES}
    gates={}
    for p in POLICIES[2:]:
        g={k:gate(summaries[k],p) for k in ("two_columns","three_columns","stress")}
        g["improvement_vs_local"]=summaries["overall"][p]["person_area"]<summaries["overall"]["local_demand"]["person_area"]
        g["passed"]=g["improvement_vs_local"] and all(g[k]["passed"] for k in ("two_columns","three_columns","stress"))
        g["strict_spillback_prevention"]=summaries["overall"][p]["total_critical_entries"]==0
        gates[p]=g
    d={"scope":"pimcat_e_grid_synthetic_not_field","sumo_version":VERSION,"sumo_validation":"EXECUTED_SYNTHETIC",
        "cases":len(rows),"trajectories":len(rows)*len(POLICIES),"horizon_seconds":HORIZON,"seeds":list(SEEDS),"policies":list(POLICIES),
        "summaries":summaries,"families":families,"gates":gates,"rows":rows,"research_gate_passed":gates["global_storage"]["passed"],
        "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","field_speed_calibration":"NOT_RUN",
        "emergency_validation":"NOT_RUN","physical_contingency_validation":"NOT_RUN",
        "candidate_promoted":False,"operationally_validated":False,"physical_actuation":False,"commercial_demo_authorized":False,"operational_decision":"abstain"}
    d["result_sha256"]=fingerprint(d);return d


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    if (root/"study.json").exists():raise ValueError("no evidence overwrite")
    d=run()
    with (root/"study.json").open("x",encoding="utf-8") as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False)
    row=next(r for r in d["rows"] if r["family"]=="outage" and r["seed"]==9100)
    for snap in row["metrics"]["global_storage"]["snapshots"]:render_svg(row["graph"],snap,root/f"heatmap-{snap['tick']}.svg")


if __name__=="__main__":main()
