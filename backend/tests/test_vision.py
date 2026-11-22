import asyncio
import hashlib
import json
from datetime import datetime, timezone
from time import monotonic,sleep
from uuid import uuid4

import cv2
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.main import create_app
from src.vision.contracts import Detection, ModelSpec
from src.vision.service import InferenceWorker
from src.vision.yolo import decode, preprocess, YoloDetector

def fixture_model(path):
    # A deterministic ONNX graph exercising a real DNN forward pass.
    # It is not a trained detector and does not measure vehicle accuracy.
    bias=np.zeros(84,np.float32)
    bias[:4]=[320,320,160,120]
    bias[4+2]=.9
    weights=np.zeros((84,3,1,1),np.float32)
    graph=helper.make_graph([
        helper.make_node("GlobalAveragePool",["images"],["pool"]),
        helper.make_node("Conv",["pool","W","B"],["head"],kernel_shape=[1,1]),
        helper.make_node("Reshape",["head","shape"],["output"]),
    ],"validation_only",[helper.make_tensor_value_info("images",TensorProto.FLOAT,[1,3,640,640])],
      [helper.make_tensor_value_info("output",TensorProto.FLOAT,[1,84,1])],
      [numpy_helper.from_array(weights,"W"),numpy_helper.from_array(bias,"B"),
       numpy_helper.from_array(np.array([1,84,1],np.int64),"shape")])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid("",12)],ir_version=8)
    onnx.checker.check_model(model)
    onnx.save(model,str(path))
    return ModelSpec(filename=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        provenance="CI deterministic fixture; NOT a trained detector",license_ref="generated test fixture")

def test_yolo_decode_letterbox_classes_nms():
    blob,geometry=preprocess(np.zeros((320,640,3),np.uint8))
    assert blob.shape==(1,3,640,640)
    raw=np.zeros((1,84,5),np.float32)
    raw[0,:4,:]=np.array([[320,320,320,320,10],[320,320,320,320,10],
                          [160,160,160,160,2],[100,100,100,100,2]])
    raw[0,6,0]=.95
    raw[0,6,1]=.85
    raw[0,9,2]=.8
    raw[0,4,3]=.99 # person is deliberately not retained
    raw[0,6,4]=.99 # outside the unpadded image
    detections=decode(raw,geometry)
    assert [d.label for d in detections]==["car","bus"]
    assert detections[0].xyxy==pytest.approx((.375,.34375,.625,.65625))
    assert Detection(label="car",confidence=.9,xyxy=(0,0,1,1)).label=="car"
    with pytest.raises(ValueError):
        Detection(label="person",confidence=.9,xyxy=(0,0,1,1))
    with pytest.raises(ValueError):
        Detection(label="car",confidence=.9,xyxy=(0,0,2,1))
    with pytest.raises(ValueError):
        decode(np.zeros((1,6,10)),geometry)
    raw[0,6,0]=np.nan
    with pytest.raises(ValueError):
        decode(raw,geometry)

def test_real_onnx_and_hash(tmp_path):
    path=tmp_path/"fixture.onnx"
    spec=fixture_model(path)
    detector=YoloDetector(spec.resolve(tmp_path),spec)
    assert detector.infer(np.zeros((96,128,3),np.uint8))[0].label=="car"
    with pytest.raises(ValueError,match="hash"):
        YoloDetector(path,spec.model_copy(update={"sha256":"0"*64}))
    with pytest.raises(ValueError):
        spec.model_copy(update={"filename":"../fixture.onnx"}).resolve(tmp_path)
    assert spec.purpose=="validation_only"

def test_worker_process_real_forward_and_shutdown(tmp_path):
    spec=fixture_model(tmp_path/"fixture.onnx")
    ok,jpeg=cv2.imencode(".jpg",np.zeros((96,128,3),np.uint8))
    assert ok
    async def run():
        worker=InferenceWorker(spec,tmp_path)
        try:
            await worker.open()
            result=await worker.infer(jpeg.tobytes())
            assert result["state"]=="ok"
            assert result["detections"][0]["label"]=="car"
            assert result["inference_ms"]>=0
        finally:
            await worker.close()
        assert worker.process is None
    asyncio.run(run())

def test_api_end_to_end_and_stale_session(tmp_path):
    spec=fixture_model(tmp_path/"fixture.onnx")
    writer=cv2.VideoWriter(str(tmp_path/"clip.avi"),cv2.VideoWriter_fourcc(*"MJPG"),15,(128,96))
    assert writer.isOpened()
    try:
        for n in range(60):
            writer.write(np.full((96,128,3),n,dtype=np.uint8))
    finally:
        writer.release()
    registry=json.dumps([{"source_id":"CAM_01","intersection_code":"CR_01","kind":"file",
                         "locator":"clip.avi","target_fps":15}])
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'test.db'}",
        vision_model_root=str(tmp_path),vision_model_json=spec.model_dump_json(),
        video_root=str(tmp_path),video_sources_json=registry)
    with TestClient(create_app(settings)) as client:
        end=monotonic()+15
        while monotonic()<end:
            status=client.get("/api/v1/vision/status").json()
            if status["state"] in {"ready","error"}:
                break
            sleep(.05)
        assert status["state"]=="ready",status
        assert client.get("/api/v1/vision/sources/MISSING/latest").status_code==404
        url="/api/v1/vision/sources/CAM_01/latest"
        assert client.get(url).status_code==404
        assert client.post("/api/v1/video/sources/CAM_01/start").status_code==202
        end=monotonic()+15
        while monotonic()<end:
            r=client.get(url)
            if r.status_code==200:
                break
            sleep(.05)
        assert r.status_code==200,r.text
        result=r.json()
        assert result["model_sha256"]==spec.sha256
        assert result["purpose"]=="validation_only"
        assert result["detections"][0]["label"]=="car"
        assert "jpeg" not in result
        health=client.get("/health").json()
        assert health["video"]["inference_connected"]
        assert health["vision"]["tracking_connected"] is False
        assert health["ingestion"]["accepted"]==0
        assert client.post("/api/v1/video/sources/CAM_01/stop").status_code==200
        assert client.get(url).status_code==404
        assert client.get("/health/live").status_code==200

@pytest.mark.parametrize("bad",["not json","{}"])
def test_bad_model_config_does_not_stop_foundation(tmp_path,bad):
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'test.db'}",vision_model_json=bad)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/vision/status").json()["error_code"]=="model_config_invalid"
        assert client.get("/health/live").status_code==200

def test_missing_model_fail_closed(tmp_path):
    spec=ModelSpec(filename="missing.onnx",sha256="0"*64,provenance="test",license_ref="test")
    settings=Settings(app_env="test",database_url=f"sqlite:///{tmp_path/'test.db'}",
                      vision_model_root=str(tmp_path),vision_model_json=spec.model_dump_json())
    with TestClient(create_app(settings)) as client:
        end=monotonic()+15
        while monotonic()<end:
            status=client.get("/api/v1/vision/status").json()
            if status["state"]=="error":
                break
            sleep(.05)
        assert status["error_code"]=="model_load_failed"
        assert client.get("/health/live").status_code==200
        assert client.get("/health").json()["video"]["inference_connected"] is False
