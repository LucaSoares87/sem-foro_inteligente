import asyncio
import json
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.main import create_app
from src.video.contracts import SourceSpec, load_sources
from src.video.manager import VideoManager, SourceBusy, child_environment

def spec(source_id="CAM_01",kind="file",locator="fixture.avi",**kwargs):
    return SourceSpec(source_id=source_id,intersection_code="CR_01",kind=kind,
                      locator=locator, target_fps=20, **kwargs)

def fixture_video(path, frames=12):
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"MJPG"),20,(96,64))
    assert writer.isOpened(), "CI requires working MJPEG encoder"
    try:
        for n in range(frames):
            image = np.full((64,96,3),n*10,dtype=np.uint8)
            writer.write(image)
    finally:
        writer.release()
    assert path.stat().st_size>0

async def wait_for(predicate,timeout=15):
    end=monotonic()+timeout
    while monotonic()<end:
        if predicate():
            return
        await asyncio.sleep(.02)
    pytest.fail("video state timeout")

@pytest.mark.parametrize("kind,locator", [
    ("file","../escape.avi"),("file","/etc/passwd"),("file","foo.txt"),
    ("webcam","9"),("rtsp","http://example.com/test"),
    ("rtsp","rtsp://"),("rtsp","rtsp://host:99999/test"),
])
def test_reject_untrusted_locator(kind,locator):
    with pytest.raises(ValueError):
        spec(kind=kind,locator=locator)

def test_registry_and_path_containment(tmp_path):
    outside=tmp_path/"external.avi"
    outside.touch()
    root=tmp_path/"video"
    root.mkdir()
    (root/"linked.avi").symlink_to(outside)
    with pytest.raises(ValueError):
        spec(locator="linked.avi").decoder_config(root)
    v={"source_id":"CAM_01","intersection_code":"CR_01","kind":"rtsp","locator":"rtsp://user:secrettest@host/live"}
    sources=load_sources(json.dumps([v]))
    assert len(sources)==1 and "secrettest" not in str(sources)
    assert "secrettest" not in str(VideoManager(sources,root).status())
    for bad in ("invalid", "null", json.dumps([v,v]),json.dumps([v]*9)):
        with pytest.raises(ValueError,match="invalid authorized video registry"):
            load_sources(bad)

def test_decoder_real_frames_and_clean_shutdown(tmp_path):
    fixture_video(tmp_path/"fixture.avi")
    async def run():
        manager=VideoManager([spec()],tmp_path)
        try:
            assert manager.status()["state"]=="idle"
            manager.start("CAM_01")
            await wait_for(lambda:manager.sessions["CAM_01"].latest is not None)
            frame=manager.take_latest("CAM_01")
            assert frame.source_id=="CAM_01" and frame.intersection_code=="CR_01"
            assert frame.width==96 and frame.height==64 and frame.decode_to_receive_ms>=0
            decoded=cv2.imdecode(np.frombuffer(frame.jpeg,np.uint8),cv2.IMREAD_COLOR)
            assert decoded.shape==(64,96,3)
            assert manager.take_latest("CAM_01") is None
            await wait_for(lambda:manager.sessions["CAM_01"].state in {"ended","error"})
            status=manager.status()["sources"][0]
            assert status["state"]=="ended",status
            assert status["frames_received"]==12
            assert status["buffer_overwrites"]>0
            assert status["last_frame_at"]
            assert status["width"]==96
            assert manager.take_latest("CAM_01") is None
            manager.start("CAM_01")
            await wait_for(lambda:manager.sessions["CAM_01"].frames>0)
            await manager.stop("CAM_01")
            assert manager.status()["active"]==0
            assert manager.sessions["CAM_01"].state=="stopped"
        finally:
            await manager.shutdown()
        with pytest.raises(SourceBusy):
            manager.start("CAM_01")
    asyncio.run(run())

def test_live_retry_is_bounded_and_independent(tmp_path):
    async def failed_spawn(config):
        raise RuntimeError("private rtsp credentials")
    async def run():
        manager=VideoManager([spec(kind="rtsp",locator="rtsp://user:secret@localhost/live",
                                   reconnect_attempts=1),spec("BAD_FILE")],tmp_path,spawn=failed_spawn)
        manager.start("CAM_01")
        manager.start("BAD_FILE")
        try:
            await wait_for(lambda:manager.sessions["CAM_01"].state=="reconnecting")
            await wait_for(lambda:manager.sessions["BAD_FILE"].state=="error")
            assert manager.sessions["BAD_FILE"].error=="invalid_source"
            await wait_for(lambda:manager.sessions["CAM_01"].state=="error")
            s=manager.status()
            assert s["sources"][0]["reconnects"]==1
            assert s["sources"][0]["error_code"]=="decoder_error"
            assert "secret" not in str(s)
        finally:
            await manager.shutdown()
    asyncio.run(run())

def test_capacity_and_cancellation(tmp_path):
    entered=0
    async def slow_spawn(config):
        nonlocal entered
        entered+=1
        await asyncio.Event().wait()
    async def run():
        sources=[spec(f"CAM_{i}",kind="webcam",locator=str(i)) for i in range(5)]
        manager=VideoManager(sources,tmp_path,spawn=slow_spawn)
        for source in sources[:4]:
            manager.start(source.source_id)
        manager.start(sources[0].source_id)
        with pytest.raises(SourceBusy):
            manager.start(sources[4].source_id)
        await wait_for(lambda:entered==4)
        await manager.stop(sources[0].source_id)
        manager.start(sources[4].source_id)
        await wait_for(lambda:entered==5)
        await manager.shutdown()
        assert manager.status()["active"]==0
        assert all(s["state"]=="stopped" for s in manager.status()["sources"])
    asyncio.run(run())

def test_api_real_decode_does_not_submit_synthetic_events(tmp_path):
    fixture_video(tmp_path/"fixture.avi",8)
    registry=json.dumps([{"source_id":"CAM_01","intersection_code":"CR_01","kind":"file",
                         "locator":"fixture.avi","target_fps":20}])
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'test.db'}",
                      video_root=str(tmp_path),video_sources_json=registry)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/video/sources").json()["registered"]==1
        assert client.post("/api/v1/video/sources/UNKNOWN/start").status_code==404
        assert client.post("/api/v1/video/sources/UNKNOWN/stop").status_code==404
        assert client.post("/api/v1/video/sources/CAM_01/start").status_code==202
        deadline=monotonic()+15
        while monotonic()<deadline:
            status=client.get("/api/v1/video/sources").json()["sources"][0]
            if status["state"] in {"ended","error"}:
                break
            sleep(.04)
        assert status["state"]=="ended",status
        assert status["frames_received"]==8
        assert client.get("/health/live").status_code==200
        health=client.get("/health").json()
        assert health["inference_engine"]=="not_loaded"
        assert health["video"]["inference_connected"] is False
        assert health["ingestion"]["accepted"]==0
        assert "locator" not in str(health["video"])
        assert client.post("/api/v1/video/sources/CAM_01/stop").json()["state"]=="stopped"

def test_child_does_not_inherit_credentials(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD","test-secret")
    monkeypatch.setenv("VIDEO_SOURCES_JSON","test-secret")
    env=child_environment()
    assert "POSTGRES_PASSWORD" not in env and "VIDEO_SOURCES_JSON" not in env
