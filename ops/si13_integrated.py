"""CI-only integrated replay test. Never connects to external cameras or traffic controllers."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE="http://127.0.0.1:5173"
SOURCE="BELLEVUE_116TH_NE12TH"
MODEL="c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
GATES={"authorized_model","physical_camera","calibration","field_ground_truth",
       "hardware_benchmark","recovery_drill","human_acceptance"}
STAGES=("vision","tracking","analytics","queue_intelligence")


def request(path,method="GET",expected=200):
    req=urllib.request.Request(BASE+path,method=method)
    try:
        with urllib.request.urlopen(req,timeout=5) as r:
            code=r.status;raw=r.read(2_000_000)
    except urllib.error.HTTPError as e:
        code=e.code;raw=e.read(2_000_000)
    if code!=expected:
        raise ValueError("unexpected HTTP status "+str(code)+" for "+path)
    return json.loads(raw)


def blocked():
    v=request("/api/v1/validation/status")
    assert v["state"]=="available" and v["framework_ready"] is True
    assert v["pilot_ready"] is False and v["operational_decision"]=="abstain" and v["physical_actuation"] is False
    assert set(v["missing_evidence"])==GATES
    assert v["runtime_observation"]["physical_sources_configured"]==0
    assert v["runtime_observation"]["authorized_candidate_model_loaded"] is False
    return {"missing":sorted(v["missing_evidence"]),"pilot_ready":False,"physical_actuation":False}


def health():
    h=request("/api/v1/health")
    assert h["status"]=="ready" and h["schema"]=="current" and h["database"]=="online"
    sources=h["video"]["sources"]
    assert len(sources)==1 and sources[0]["source_id"]==SOURCE
    assert sources[0]["kind"]=="file" and sources[0]["data_origin"]=="external_real_replay"
    assert sources[0]["commercial_demo_authorized"] is False
    assert h["vision"]["purpose"]=="validation_only" and h["vision"]["model_sha256"]==MODEL
    assert h["optimization"]["physical_actuation"] is False and h["optimization"]["operational_decision"]=="abstain"
    assert h["vision"]["state"]!="error"
    assert all(h[s].get("failed",0)==0 for s in STAGES)
    assert h["optimization"]["failed"]==0 and h["queue_persistence"]["failed"]==0
    return h


def wait_for(predicate,seconds=60):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        h=health()
        if predicate(h):return h
        time.sleep(.5)
    raise TimeoutError("required pipeline condition not met")


def capture(h):
    s=h["video"]["sources"][0]
    return {"frames_received":s["frames_received"],"buffer_overwrites":s["buffer_overwrites"],
        "target_fps":s["target_fps"],"measured_fps":s["measured_fps"],
        "stage_processed":{k:h[k]["processed"] for k in STAGES},
        "queue_saved":h["queue_persistence"]["saved"],"vision_discarded":h["vision"]["discarded"]}


def run_cmd(args,out=None,expected=0):
    p=subprocess.run(args,text=True,capture_output=True,timeout=150)
    if p.returncode!=expected:
        raise RuntimeError("unexpected command exit "+str(p.returncode)+": "+p.stderr[-600:])
    if out is not None:
        Path(out).write_text(p.stdout,encoding="utf-8")
    return p.stdout


def start():
    request("/api/v1/video/sources/"+SOURCE+"/start","POST",202)
    h=wait_for(lambda x:x["video"]["sources"][0]["state"]=="running" and
               all(x[k]["processed"]>=3 for k in STAGES) and x["queue_persistence"]["saved"]>=1)
    # The queue and optimizer reads are individually current. Retry to handle different HTTP snapshots.
    for _ in range(20):
        try:
            q=request("/api/v1/queue/sources/"+SOURCE+"/latest")
            o=request("/api/v1/optimization/sources/"+SOURCE+"/latest")
        except ValueError:
            time.sleep(.15);continue
        assert q["data_origin"]=="external_real_replay" and q["physical_speed_available"] is False
        assert o["origin"]=="external_real_replay" and o["operational_decision"]=="abstain"
        assert o["physical_actuation"] is False and o["operationally_validated"] is False
        assert o["preferred_in_simulation"]=="abstain" and o["dynamic_x_safe_vehicles"] is None
        if q["frame_sequence"]==o["frame_sequence"]:
            return h,q["session_id"]
    raise RuntimeError("no corresponding experimental queue/optimization read")


def stop():
    request("/api/v1/video/sources/"+SOURCE+"/stop","POST")
    wait_for(lambda h:h["video"]["sources"][0]["state"]=="stopped")
    request("/api/v1/queue/sources/"+SOURCE+"/latest",expected=404)
    request("/api/v1/optimization/sources/"+SOURCE+"/latest",expected=404)
    assert request("/api/v1/optimization/status")["sources"]==[]


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    assert not (out/"integrated.json").exists()
    before_blocked=blocked()
    initial=wait_for(lambda h:h["vision"]["state"]=="ready")
    assert initial["video"]["sources"][0]["state"]=="idle"
    h,session=start()
    before=capture(h)
    probe=out/"replay-probe.json"
    # Actual concurrent HTTP and replay load; keep load and inference measurements separate.
    load=subprocess.Popen([sys.executable,"ops/smoke_load.py","--url",BASE+"/api/v1/health",
        "--requests","120","--concurrency","8","--p95-ms","5000"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        run_cmd([sys.executable,"ops/pilot_probe.py","--samples","20","--interval",".5","--output",str(probe)])
        stdout,stderr=load.communicate(timeout=120)
        if load.returncode!=0:raise RuntimeError("HTTP load failed: "+stderr[-600:])
        (out/"http-load.json").write_text(stdout)
    finally:
        if load.poll() is None:load.kill();load.communicate()
    after=capture(health())
    delta={k:after["stage_processed"][k]-before["stage_processed"][k] for k in STAGES}
    assert all(v>0 for v in delta.values())
    assert after["frames_received"]>before["frames_received"]
    assert blocked()==before_blocked
    # The same replay must NOT qualify as a physical workload.
    run_cmd([sys.executable,"ops/pilot_probe.py","--samples","3","--interval",".1","--require-workload",
        "--output",str(out/"field-probe-rejected.json")],expected=5)
    first_history=request("/api/v1/queue/sources/"+SOURCE+"/history")["items"]
    assert first_history
    # Recover while replay running; verify readiness AND new inference and queue processing.
    run_cmd([sys.executable,"ops/recovery_drill.py","--component","backend","--max-seconds","60",
        "--output",str(out/"backend-recovery.json")])
    recovered=wait_for(lambda h:h["vision"]["state"]=="ready")
    assert recovered["video"]["sources"][0]["state"]=="idle"
    request("/api/v1/optimization/sources/"+SOURCE+"/latest",expected=404)
    h2,session2=start()
    assert session2!=session
    stop()
    # Persistence should survive backend restart and source stop.
    second_history=request("/api/v1/queue/sources/"+SOURCE+"/history")["items"]
    assert any(r["session_id"]==session for r in second_history)
    assert any(r["session_id"]==session2 for r in second_history)
    assert blocked()==before_blocked
    run_cmd([sys.executable,"ops/recovery_drill.py","--component","postgres","--max-seconds","60",
        "--output",str(out/"postgres-recovery.json")])
    assert blocked()==before_blocked
    assert len(request("/api/v1/queue/sources/"+SOURCE+"/history")["items"])>=len(second_history)
    # Backup into scratch, restore only to alternate CI DB; store report, not DB contents.
    scratch=out.parent/"si13-private-db"
    scratch.mkdir(exist_ok=False)
    backup=scratch/"test.dump"
    run_cmd(["sh","ops/backup.sh",str(backup)])
    run_cmd(["sh","ops/restore.sh",str(backup),"traffic_restore_si13"],out/"restore.txt")
    # Compare recovered tables' record counts in both databases after stopping the replay.
    sql="SELECT count(*) FROM queue_states"
    # Table names from the migration are checked by CI; inspect via PostgreSQL catalog if necessary.
    counts={}
    for db in ("traffic","traffic_restore_si13"):
        output=run_cmd(["docker","compose","exec","-T","postgres","psql","-U","traffic","-d",db,"-Atqc",sql])
        counts[db]=int(output.strip())
    assert counts["traffic"]>0 and counts["traffic"]==counts["traffic_restore_si13"]
    result={"scope":"isolated_external_real_replay_not_field","before":before,"after":after,
        "stage_delta":delta,"post_recovery":capture(h2),"new_session_confirmed":True,
        "stopped_source_no_current_result":True,"history_survived_restart":True,
        "backup_sha256":hashlib.sha256(backup.read_bytes()).hexdigest(),"restored_counts":counts,
        "field_probe_exit":5,"gates":before_blocked,"field_accuracy_measured":False,
        "pilot_ready":False,"physical_actuation":False,"operational_decision":"abstain",
        "candidate_promoted":False}
    result["artifact_sha256"]=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    with (out/"integrated.json").open("x") as f:json.dump(result,f,indent=2,sort_keys=True)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
