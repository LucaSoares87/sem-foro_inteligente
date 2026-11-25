import asyncio
import json
import os
import subprocess
from pathlib import Path
from time import monotonic
import pytest
from src.video.contracts import SourceSpec,load_sources
from src.video.manager import VideoManager
from test_video import wait_for

def spec(**kw):
    d=dict(source_id="LAB_01",intersection_code="LAB_CR",kind="rtsp",locator="rtsp://127.0.0.1:18554/synthetic",continuous=True,authorization_ref="local-synthetic-lab-only",reconnect_attempts=0,target_fps=5)
    d.update(kw);return SourceSpec(**d)

def test_opt_in_requires_explicit_authorized_live_source():
    for change in (dict(authorization_ref=None),dict(kind="file",locator="fixture.avi"),dict(continuous="true")):
        with pytest.raises(ValueError):spec(**change)
    raw=[dict(source_id=f"CAM_{i}",intersection_code="CR_01",kind="rtsp",locator="rtsp://127.0.0.1/live",continuous=True,authorization_ref="local-test-only") for i in range(5)]
    with pytest.raises(ValueError):load_sources(json.dumps(raw))

def test_supervision_failure_and_manual_stop(tmp_path):
    calls=[]
    async def fail(config):
        calls.append(1);raise RuntimeError("private locator")
    async def run():
        manager=VideoManager([spec()],tmp_path,spawn=fail)
        try:
            manager.start_supervisor()
            await wait_for(lambda:len(calls)>=2,timeout=12)
            assert manager.gateway_status()["sources"][0]["supervisor_restarts"]>=1
            await manager.stop("LAB_01")
            n=len(calls);await asyncio.sleep(.6)
            row=manager.gateway_status()["sources"][0]
            assert len(calls)==n and not row["desired"] and row["observation"]=="unknown"
            assert "private locator" not in str(manager.gateway_status())
            manager.start("LAB_01");await wait_for(lambda:len(calls)>n)
        finally:await manager.shutdown()
        assert manager.supervisor_task is None and manager.status()["active"]==0
    asyncio.run(run())

@pytest.mark.skipif(os.environ.get("PIMCAT_H1_RTSP_REQUIRED")!="1",reason="private loopback streaming CI only")
def test_real_rtsp_interruption_recovery(tmp_path):
    def publisher():
        return subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-re","-f","lavfi","-i","testsrc2=size=320x240:rate=10",
          "-c:v","libx264","-preset","ultrafast","-tune","zerolatency","-g","10","-f","rtsp","-rtsp_transport","tcp","rtsp://127.0.0.1:18554/synthetic"],
          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    async def run():
        p=publisher();manager=VideoManager([spec()],tmp_path)
        try:
            await asyncio.sleep(2);assert p.poll() is None
            started=monotonic();manager.start_supervisor()
            s=manager.sessions["LAB_01"]
            await wait_for(lambda:s.state=="running" and s.frames>=10,timeout=30)
            first=manager.gateway_status()["sources"][0];sid=s.session_id
            p.terminate();p.wait(timeout=10)
            await wait_for(lambda:s.state=="error",timeout=20)
            lost=manager.gateway_status()["sources"][0]
            assert lost["observation"]=="unknown"
            p=publisher();resumed=monotonic()
            await wait_for(lambda:s.state=="running" and s.frames>=10 and s.session_id!=sid,timeout=45)
            recovered=manager.gateway_status()["sources"][0]
            assert recovered["process_observed_frames"]>=first["process_observed_frames"]+10
            assert recovered["supervisor_restarts"]>=1 and recovered["observation"]=="recent_frames"
            recovery=monotonic()-resumed
            await manager.stop("LAB_01");await asyncio.sleep(6)
            stopped=manager.gateway_status()["sources"][0]
            assert stopped["capture_state"]=="stopped" and not stopped["desired"] and stopped["observation"]=="unknown"
            manager.start("LAB_01");await wait_for(lambda:s.state=="running" and s.frames>=5,timeout=30)
            report={"scope":"synthetic_loopback_rtsp_not_field","initial":first,"interrupted":lost,"recovered":recovered,"manual_stop":stopped,
              "explicit_restart":manager.gateway_status()["sources"][0],"elapsed_seconds":monotonic()-started,
              "recovery_observed_seconds":recovery,"soak_24h":"NOT_RUN","rtsps":"NOT_RUN","municipal":"BLOCKED","physical_actuation":False}
            Path(os.environ["PIMCAT_H1_REPORT"]).write_text(json.dumps(report,indent=2))
        finally:
            await manager.shutdown()
            if p.poll() is None:p.terminate();p.wait(timeout=10)
    asyncio.run(run())
