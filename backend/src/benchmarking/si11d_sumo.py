"""Isolated microscopic research. libsumo is in-process and never connects to a controller."""
import argparse
import json
import math
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import deque
from importlib.metadata import version
from pathlib import Path
from random import Random
from statistics import fmean

from src.archive.store import fingerprint
from src.benchmarking.si11c_predictive_x import CYCLE, CYCLES, SERVICE, TRANSITION, select, schedule
from src.validation.io import sha256_file

VERSION="1.24.0"
HORIZON=CYCLE*CYCLES
SEEDS=tuple(range(5000,5004))
POLICIES=("fixed_alternating","demand_proportional","predictive_x","predictive_no_x")
LANES=("a_in_0","b_in_0")
# length in metres, nominal arrival probabilities per tick, scenario pattern.
FAMILIES={
    "balanced":(240,(.20,.20),"steady"),
    "asymmetric":(240,(.10,.30),"steady"),
    "heavy":(240,(.30,.36),"steady"),
    "low":(240,(.06,.10),"steady"),
    "compact":(105,(.15,.32),"steady"),
    "compact_burst":(105,(.12,.28),"burst"),
    "shift":(180,(.20,.26),"shift"),
    "overloaded":(105,(.34,.40),"steady"),
}
COHORTS={"steady_long":tuple(FAMILIES)[:4],"shift_and_storage":tuple(FAMILIES)[4:]}
CAR_LENGTH=5.
MIN_GAP=2.5
# Nominal service assumption shared by adaptive policies, not a measured calibration.
NOMINAL_SERVICE=.5


def write_xml(path,root):
    ET.ElementTree(root).write(path,encoding="utf-8",xml_declaration=True)


def build_network(root,length):
    if length not in {v[0] for v in FAMILIES.values()}:
        raise ValueError("unregistered synthetic length")
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    nodes=ET.Element("nodes")
    for name,x,y,kind in (("W",-length,0,"priority"),("S",0,-length,"priority"),
                          ("J",0,0,"traffic_light"),("E",160,0,"priority"),("N",0,160,"priority")):
        ET.SubElement(nodes,"node",id=name,x=str(x),y=str(y),type=kind)
    edges=ET.Element("edges")
    for name,start,end in (("a_in","W","J"),("b_in","S","J"),("a_out","J","E"),("b_out","J","N")):
        ET.SubElement(edges,"edge",id=name,attrib={"from":start,"to":end,"numLanes":"1","speed":"13.89"})
    connections=ET.Element("connections")
    for g in ("a","b"):
        ET.SubElement(connections,"connection",attrib={"from":g+"_in","to":g+"_out","fromLane":"0","toLane":"0"})
    for name,tree in (("nodes",nodes),("edges",edges),("connections",connections)):
        write_xml(root/(name+".xml"),tree)
    exe=shutil.which("netconvert")
    if not exe:
        raise ValueError("pinned netconvert not installed")
    output=root/"network.net.xml"
    subprocess.run([exe,"--node-files",str(root/"nodes.xml"),"--edge-files",str(root/"edges.xml"),
        "--connection-files",str(root/"connections.xml"),"--no-turnarounds","true",
        "--output-file",str(output)],check=True,capture_output=True,text=True,timeout=30)
    tree=ET.parse(output)
    links=[c for c in tree.findall("connection") if c.get("tl")=="J"]
    if {(c.get("from"),c.get("to")) for c in links}!={("a_in","a_out"),("b_in","b_out")} or len(links)!=2:
        raise ValueError("unexpected synthetic junction movements")
    if {int(c.get("linkIndex")) for c in links}!={0,1}:
        raise ValueError("unexpected signal indices")
    junction=tree.find("./junction[@id='J']")
    requests=junction.findall("request")
    # Both movements must conflict in the generated network.
    if len(requests)!=2 or any("1" not in req.get("foes","") for req in requests):
        raise ValueError("expected crossing conflicts absent")
    return output


def demand(family,seed):
    length,rates,pattern=FAMILIES[family]
    if seed%2:
        rates=rates[::-1]
    rng=Random(seed)
    rows=[]
    for t in range(HORIZON):
        for g,rate in enumerate(rates):
            p=rate
            if pattern=="burst":
                p*=1.8 if t%30<15 else .2
            elif pattern=="shift":
                p*=1.6 if (t//CYCLE+g)%2==0 else .4
            if rng.random()<min(1.,p):
                rows.append((t,g,f"v_{t}_{g}"))
    return rates,tuple(rows)


def write_routes(path,rows):
    root=ET.Element("routes")
    ET.SubElement(root,"vType",id="car",length=str(CAR_LENGTH),minGap=str(MIN_GAP),
                  accel="2.6",decel="4.5",sigma="0.0",tau="1.0",maxSpeed="13.89",speedFactor="1.0")
    for g in ("a","b"):
        ET.SubElement(root,"route",id=g,edges=g+"_in "+g+"_out")
    for t,g,vid in rows:
        ET.SubElement(root,"vehicle",id=vid,type="car",route="ab"[g],depart=str(t),departSpeed="0")
    write_xml(path,root)


def states(indices,action):
    """Same synthetic budget as SI-11C, with 3 yellow + 1 all-red per transition."""
    first,w=action
    schedule(action)  # validates bounds and 60 ticks
    def state(g,color):
        a=["r","r"]; a[indices[g]]=color
        return "".join(a)
    result=[state(first,"G")]*w+[state(first,"y")]*3+["rr"]
    result += [state(1-first,"G")]*(SERVICE-w)+[state(1-first,"y")]*3+["rr"]
    assert len(result)==CYCLE and result.count("rr")==2
    assert sum("G" in s for s in result)==SERVICE
    assert all(s.count("G")<=1 and s.count("y")<=1 for s in result)
    return result


def ensure_version():
    import libsumo
    for name in ("eclipse-sumo","libsumo","sumolib","traci"):
        if version(name)!=VERSION:
            raise ValueError("SUMO package version mismatch: "+name)
    return libsumo


def trajectory(api,network,routes,rows,rates,seed,policy):
    planned={vid:(t,g) for t,g,vid in rows}
    inserted=set(); arrived=set(); wait={}; scheduled=set()
    ids_by_time={}
    for t,g,vid in rows:
        ids_by_time.setdefault(t,[]).append(vid)
    area=critical=blocked=peak=0.
    plans=[]; green=[0,0]; fallback=0; collisions=teleports=0
    api.start(["sumo","-n",str(network),"-r",str(routes),"--seed",str(seed),
        "--step-length","1","--route-steps","0","--time-to-teleport","-1",
        "--max-depart-delay","-1","--collision.action","warn","--no-step-log","true",
        "--duration-log.disable","true","--end",str(HORIZON)])
    try:
        actual=api.getVersion()[1]
        if actual.split()[-1]!=VERSION:
            raise ValueError("SUMO runtime version mismatch: "+actual)
        if tuple(api.trafficlight.getIDList())!=("J",):
            raise ValueError("unexpected traffic light")
        links=api.trafficlight.getControlledLinks("J")
        if len(links)!=2 or any(len(x)!=1 for x in links):
            raise ValueError("unexpected controlled links")
        indices=tuple(next(i for i,x in enumerate(links) if x[0][0]==lane) for lane in LANES)
        if len(set(indices))!=2:
            raise ValueError("signal mapping mismatch")
        lengths=[api.lane.getLength(l) for l in LANES]
        caps=[max(1,math.floor(v/(CAR_LENGTH+MIN_GAP))) for v in lengths]
        pair=tuple((0,rates[g],NOMINAL_SERVICE,caps[g]) for g in (0,1))
        for t in range(HORIZON):
            if t%CYCLE==0:
                # Only current simulated stopped vehicles and nominal demand are exposed to the policy.
                queues=[]
                for lane in LANES:
                    halted=[v for v in api.lane.getLastStepVehicleIDs(lane) if api.vehicle.getSpeed(v)<.1]
                    queues.append(deque(sorted((t-int(wait.get(v,0)) for v in halted))))
                action,reason=select(policy,pair,queues,t)
                if action is None:
                    fallback+=1
                    action=(t//CYCLE%2,26) # synthetic accounting fallback only
                plan=states(indices,action)
                plans.append({"first":action[0],"window":action[1],"reason":reason})
                green[action[0]]+=action[1]; green[1-action[0]]+=SERVICE-action[1]
            scheduled.update(ids_by_time.get(t,()))
            signal=plan[t%CYCLE]
            api.trafficlight.setRedYellowGreenState("J",signal)
            if api.trafficlight.getRedYellowGreenState("J")!=signal:
                raise AssertionError("simulation phase mismatch")
            api.simulationStep()
            new=set(api.simulation.getDepartedIDList())
            done=set(api.simulation.getArrivedIDList())
            if new&inserted or done&arrived or not new<=scheduled:
                raise AssertionError("duplicate or unscheduled vehicle")
            inserted.update(new); arrived.update(done)
            active=set(api.vehicle.getIDList())
            pending=scheduled-inserted
            if not arrived<=inserted or active!=(inserted-arrived):
                raise AssertionError("vehicle accounting mismatch")
            # Count stopped time across the network AND departure insertion delay.
            halted={v for v in active if api.vehicle.getSpeed(v)<.1}
            for v in halted|pending:
                wait[v]=wait.get(v,0)+1
            area+=len(halted)+len(pending)
            occ=[api.lane.getLastStepVehicleNumber(l) for l in LANES]
            critical+=sum(max(0.,occ[g]-.85*caps[g]) for g in (0,1))
            blocked+=len(pending)
            peak=max(peak,len(halted)+len(pending))
            collisions+=api.simulation.getCollidingVehiclesNumber()
            teleports+=api.simulation.getStartingTeleportNumber()
        if scheduled!=set(planned) or len(inserted)!=len(arrived)+len(active):
            raise AssertionError("final conservation failed")
        if sum(green)!=SERVICE*CYCLES or min(green)<12*CYCLES:
            raise AssertionError("unequal opportunity budget")
        return {"runtime_version":actual,"scheduled":len(planned),"inserted":len(inserted),
            "departed_network":len(arrived),"remaining_network":len(active),
            "uninserted":len(planned)-len(inserted),"queue_area_with_pending_vehicle_seconds":area,
            "pending_vehicle_seconds":blocked,"critical_occupancy_exposure_vehicle_seconds":critical,
            "peak_stopped_plus_pending":peak,"max_accumulated_stopped_or_pending_seconds":max(wait.values(),default=0),
            "green_ticks":green,"fallbacks":fallback,"colliding_vehicle_events":collisions,
            "teleports":teleports,"lane_lengths_m":lengths,"nominal_capacity":caps,"plans":plans}
    finally:
        api.close()


def case(api,root,family,seed):
    length,_,_=FAMILIES[family]
    root=Path(root)
    network=build_network(root,length)
    rates,rows=demand(family,seed)
    route=root/"demand.rou.xml"
    write_routes(route,rows)
    metrics={p:trajectory(api,network,route,rows,rates,seed,p) for p in POLICIES}
    return {"family":family,"seed":seed,"nominal_rates":rates,"scheduled":len(rows),
        "network_sha256":sha256_file(network),"demand_sha256":sha256_file(route),
        "metrics":metrics}


FIELDS=("queue_area_with_pending_vehicle_seconds","departed_network","uninserted",
        "pending_vehicle_seconds","critical_occupancy_exposure_vehicle_seconds",
        "max_accumulated_stopped_or_pending_seconds","peak_stopped_plus_pending")


def summarize(rows):
    means={p:{k:fmean(r["metrics"][p][k] for r in rows) for k in FIELDS} for p in POLICIES}
    cand=means["predictive_x"]
    gates={}
    for p in ("fixed_alternating","demand_proportional"):
        b=means[p]
        gates[p]={
            "queue_area_noninferiority_5pct":cand[FIELDS[0]]<=1.05*b[FIELDS[0]],
            "throughput_noninferiority_5pct":cand[FIELDS[1]]>=.95*b[FIELDS[1]],
            "uninserted_not_increased":cand[FIELDS[2]]<=b[FIELDS[2]],
            "pending_delay_not_increased":cand[FIELDS[3]]<=b[FIELDS[3]],
            "critical_exposure_not_increased":cand[FIELDS[4]]<=b[FIELDS[4]],
            "max_wait_noninferiority_5pct":cand[FIELDS[5]]<=1.05*b[FIELDS[5]]}
    events={p:{k:sum(r["metrics"][p][k] for r in rows) for k in
        ("fallbacks","colliding_vehicle_events","teleports")} for p in POLICIES}
    improvement=cand[FIELDS[0]]<means["fixed_alternating"][FIELDS[0]] or cand[FIELDS[4]]<means["fixed_alternating"][FIELDS[4]]
    return {"cases":len(rows),"means":means,"gates":gates,"events":events,
        "improvement_vs_fixed":improvement,
        "all_research_gates_met":improvement and not any(events["predictive_x"].values())
          and all(not (e["colliding_vehicle_events"] or e["teleports"]) for e in events.values())
          and all(all(g.values()) for g in gates.values())}


def run():
    api=ensure_version()
    p=((0,.1,.5,20),(0,.2,.5,20))
    assert select("predictive_x",p,[deque(),deque()],0,.64)[0] is None
    with tempfile.TemporaryDirectory(prefix="si11d-") as d:
        rows=[case(api,Path(d)/f"{f}-{s}",f,s) for f in FAMILIES for s in SEEDS]
    cohorts={c:summarize([r for r in rows if r["family"] in fs]) for c,fs in COHORTS.items()}
    result={"schema_version":1,"scope":"synthetic_microscopic_sumo_not_field","sumo_version":VERSION,
        "sumo_validation":"EXECUTED_SYNTHETIC","seeds":list(SEEDS),"cycles":CYCLES,"horizon_seconds":HORIZON,
        "overall":summarize(rows),"cohorts":cohorts,
        "families":{f:summarize([r for r in rows if r["family"]==f]) for f in FAMILIES},
        "cases":rows,"research_gate_passed":all(v["all_research_gates_met"] for v in cohorts.values()),
        "low_confidence_abstention_verified":True,"candidate_promoted":False,"x_validated_for_real_traffic":False,
        "commercial_demo_authorized":False,"operationally_validated":False,"physical_actuation":False}
    result["result_sha256"]=fingerprint(result)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    a=p.parse_args()
    output=Path(a.output)
    if output.exists():
        raise ValueError("no evidence overwrite")
    report=run()
    with output.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,sort_keys=True,allow_nan=False)


if __name__=="__main__":
    main()
