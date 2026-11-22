import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import sys
from time import monotonic

from src.video.manager import child_environment, close_decoder
from src.vision.contracts import DetectionBatch, ModelSpec
from src.vision.worker import LENGTH

class InferenceWorker:
    def __init__(self,spec,root):
        self.spec,self.root=spec,root
        self.process=None

    async def _reply(self):
        raw=await self.process.stdout.readline()
        if not raw or len(raw)>65536:
            raise ValueError("invalid inference response")
        return json.loads(raw)

    async def open(self):
        self.process=await asyncio.create_subprocess_exec(
            sys.executable,"-m","src.vision.worker",stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            env=child_environment(),limit=65536)
        payload={"spec":self.spec.model_dump(mode="json"),"root":str(self.root)}
        async with asyncio.timeout(30):
            self.process.stdin.write(json.dumps(payload).encode()+b"\n")
            await self.process.stdin.drain()
            if (await self._reply()).get("state")!="ready":
                raise ValueError("model_load_failed")

    async def infer(self,jpeg):
        async with asyncio.timeout(10):
            self.process.stdin.write(LENGTH.pack(len(jpeg))+jpeg)
            await self.process.stdin.drain()
            data=await self._reply()
            if data.get("state")!="ok":
                raise ValueError("inference_failed")
            return data

    async def close(self):
        if self.process is not None:
            await close_decoder(self.process)
            self.process=None

class VisionService:
    """One isolated CPU worker, round-robin across existing latest-frame buffers."""
    def __init__(self,video,spec: ModelSpec|None,root,worker_factory=InferenceWorker):
        self.video,self.spec,self.root=video,spec,root
        self.worker_factory=worker_factory
        self.state="not_loaded"
        self.error=None
        self.task=None
        self.results={}
        self.processed=self.discarded=0

    def start(self):
        if self.spec is None or self.task is not None:
            return
        self.state="loading"
        self.task=asyncio.create_task(self._run(),name="vision-worker")

    def valid_result(self,source_id):
        batch=self.results.get(source_id)
        session=self.video.sessions.get(source_id)
        if batch is None or session is None or session.session_id!=batch.session_id:
            return None
        if session.state not in {"running","ended"}:
            return None
        if session.state=="running" and (datetime.now(timezone.utc)-batch.received_at).total_seconds()>5:
            return None
        return batch

    async def _run(self):
        worker=self.worker_factory(self.spec,self.root)
        try:
            await worker.open()
            self.state="ready"
            while True:
                found=False
                for source_id,session in self.video.sessions.items():
                    if session.state!="running":
                        continue
                    frame=self.video.take_latest(source_id)
                    if frame is None:
                        continue
                    found=True
                    data=await worker.infer(frame.jpeg)
                    batch=DetectionBatch(source_id=frame.source_id,intersection_code=frame.intersection_code,
                        session_id=frame.session_id,frame_sequence=frame.sequence,received_at=frame.received_at,
                        inferred_at=datetime.now(timezone.utc),model_sha256=self.spec.sha256,purpose=self.spec.purpose,
                        inference_ms=data["inference_ms"],detections=data["detections"])
                    if session.session_id!=frame.session_id or session.state not in {"running","ended"}:
                        self.discarded+=1
                        continue
                    self.results[source_id]=batch
                    self.processed+=1
                if not found:
                    await asyncio.sleep(.04)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.error="model_load_failed" if self.state=="loading" else "inference_failed"
            self.state="error"
            self.results.clear()
        finally:
            await worker.close()

    async def shutdown(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
            self.task=None
        self.results.clear()
        self.state="not_loaded"

    def status(self):
        sources=[]
        for source_id,session in self.video.sessions.items():
            batch=self.valid_result(source_id)
            if batch is not None:
                sources.append({"source_id":source_id,"intersection_code":batch.intersection_code,
                    "frame_sequence":batch.frame_sequence,"source_state":session.state,
                    "live":session.state=="running","inference_ms":batch.inference_ms,
                    "detections_per_frame":len(batch.detections),
                    "classes":dict(Counter(d.label for d in batch.detections)),
                    "inferred_at":batch.inferred_at.isoformat()})
        return {"state":self.state,"backend":"opencv_dnn_cpu","configured":self.spec is not None,
                "purpose":self.spec.purpose if self.spec else None,
                "model_sha256":self.spec.sha256 if self.spec else None,
                "processed":self.processed,"discarded":self.discarded,"error_code":self.error,
                "sources":sources,"tracking_connected":False,"decision_mode":"abstention_only"}
