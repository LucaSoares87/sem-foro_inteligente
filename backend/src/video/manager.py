import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import monotonic, monotonic_ns
from uuid import uuid4

from src.video.contracts import MAX_ACTIVE, MAX_HEIGHT, MAX_JPEG, MAX_WIDTH, SourceSpec, VideoFrame
from src.video.protocol import HEADER

class SourceBusy(Exception):
    pass

class CaptureError(Exception):
    pass

def child_environment():
    # Decoder does not inherit database passwords or video registry secrets.
    names = {"PATH","SYSTEMROOT","WINDIR","TEMP","TMP","TMPDIR","LANG","LC_ALL","LD_LIBRARY_PATH"}
    return {k:v for k,v in os.environ.items() if k.upper() in names}

async def spawn_decoder(config):
    process = await asyncio.create_subprocess_exec(
        sys.executable,"-m","src.video.worker",stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=child_environment())
    try:
        process.stdin.write(json.dumps(config).encode())
        await process.stdin.drain()
        process.stdin.close()
        return process
    except BaseException:
        await close_decoder(process)
        raise

async def close_decoder(process):
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.communicate()

class VideoSession:
    def __init__(self,spec: SourceSpec,root: Path,spawn=spawn_decoder):
        self.spec,self.root,self.spawn = spec,root,spawn
        self.task = None
        self.session_id = uuid4()
        self.stopping = False
        self.stop_lock = asyncio.Lock()
        self.state = "idle"
        self.error = None
        self.latest = None
        self.frames = self.overwritten = self.reconnects = 0
        self.arrivals = deque(maxlen=30)
        self.last_frame_at = None
        self.last_delay_ms = None
        self.dimensions = None

    def active(self):
        return self.task is not None and not self.task.done()

    def start(self):
        if self.stopping:
            raise SourceBusy
        if self.active():
            return
        self.session_id = uuid4()
        self.latest = None
        self.frames = self.overwritten = self.reconnects = 0
        self.arrivals.clear()
        self.last_frame_at = self.last_delay_ms = self.dimensions = self.error = None
        self.state = "starting"
        self.task = asyncio.create_task(self._run(),name=f"video-{self.spec.source_id}")

    async def stop(self):
        async with self.stop_lock:
            self.stopping = True
            try:
                if self.active():
                    self.task.cancel()
                    await asyncio.gather(self.task,return_exceptions=True)
                self.latest = None
                self.arrivals.clear()
                self.state = "stopped"
            finally:
                self.stopping = False

    def take_latest(self):
        frame,self.latest = self.latest,None
        return frame

    async def _capture(self):
        try:
            config = self.spec.decoder_config(self.root)
        except (ValueError,OSError):
            raise CaptureError("invalid_source") from None
        self.session_id = uuid4()
        process = await self.spawn(config)
        sequence = 0
        try:
            while True:
                try:
                    async with asyncio.timeout(10 if sequence==0 else 5):
                        header = await process.stdout.readexactly(HEADER.size)
                        width,height,number,decoded,size = HEADER.unpack(header)
                        if not (1<=width<=MAX_WIDTH and 1<=height<=MAX_HEIGHT and
                                1<=size<=MAX_JPEG and number==sequence+1 and 0<decoded<=monotonic_ns()):
                            raise CaptureError("invalid_decoder_protocol")
                        try:
                            jpeg = await process.stdout.readexactly(size)
                        except asyncio.IncompleteReadError:
                            raise CaptureError("invalid_decoder_protocol") from None
                        if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                            raise CaptureError("invalid_decoder_protocol")
                except asyncio.IncompleteReadError as exc:
                    if exc.partial:
                        raise CaptureError("invalid_decoder_protocol") from None
                    async with asyncio.timeout(2):
                        code = await process.wait()
                    if code==0 and self.spec.kind=="file" and sequence:
                        return
                    raise CaptureError("source_unavailable" if not sequence else "stream_interrupted") from None
                sequence = number
                self.frames += 1
                now = datetime.now(timezone.utc)
                self.last_delay_ms = max(0,(monotonic_ns()-decoded)/1_000_000)
                self.last_frame_at = now
                self.dimensions = (width,height)
                self.arrivals.append(monotonic())
                if self.latest is not None:
                    self.overwritten += 1
                self.latest = VideoFrame(self.spec.source_id,self.spec.intersection_code,
                    self.frames,width,height,now,self.last_delay_ms,jpeg,self.session_id)
                self.state,self.error = "running",None
        finally:
            await close_decoder(process)

    async def _run(self):
        try:
            while True:
                try:
                    await self._capture()
                    self.state = "ended"
                    return
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    self.error = "decoder_timeout"
                except CaptureError as exc:
                    self.error = str(exc)
                except Exception:
                    self.error = "decoder_error"
                self.latest = None
                self.arrivals.clear()
                if (self.spec.kind=="file" or self.error=="invalid_source" or
                        self.reconnects>=self.spec.reconnect_attempts):
                    self.state = "error"
                    return
                self.reconnects += 1
                self.state = "reconnecting"
                await asyncio.sleep(min(2**(self.reconnects-1),8))
        finally:
            self.latest = None

    def status(self):
        fps = None
        if self.state=="running" and len(self.arrivals)>1 and self.arrivals[-1]>self.arrivals[0]:
            fps = (len(self.arrivals)-1)/(self.arrivals[-1]-self.arrivals[0])
        return {"source_id":self.spec.source_id,"intersection_code":self.spec.intersection_code,
                "kind":self.spec.kind,"data_origin":self.spec.data_origin,
                "commercial_demo_authorized":self.spec.commercial_demo_authorized,
                "state":self.state,"error_code":self.error,
                "frames_received":self.frames,"buffer_overwrites":self.overwritten,
                "reconnects":self.reconnects,"target_fps":self.spec.target_fps,
                "measured_fps":fps,"decode_to_receive_ms":self.last_delay_ms,
                "last_frame_at":self.last_frame_at.isoformat() if self.last_frame_at else None,
                "width":self.dimensions[0] if self.dimensions else None,
                "height":self.dimensions[1] if self.dimensions else None,
                "frame_available":self.latest is not None}

class VideoManager:
    def __init__(self,sources,root,spawn=spawn_decoder):
        self.sessions = {s.source_id:VideoSession(s,Path(root),spawn) for s in sources}
        self.closing = False
        self.desired = {s.source_id for s in sources if s.continuous}
        self.supervisor_task = None
        self.supervision = {s.source_id: {"restarts":0,"next":0.,"cooldown":5.,"stable":None,
            "seen_frames":0,"total_frames":0,"seen_session_task":None} for s in sources if s.continuous}

    def start_supervisor(self):
        if self.desired and self.supervisor_task is None and not self.closing:
            self.supervisor_task = asyncio.create_task(self._supervise(),name="video-supervisor")

    def _sample(self,key,now):
        s=self.sessions[key];m=self.supervision[key]
        if m["seen_session_task"] is not s.task:
            m["seen_session_task"]=s.task;m["seen_frames"]=0;m["stable"]=None
        m["total_frames"]+=max(0,s.frames-m["seen_frames"])
        m["seen_frames"]=s.frames
        if s.state=="running" and s.arrivals and now-s.arrivals[-1]<=5:
            if m["stable"] is None:m["stable"]=now
            if now-m["stable"]>=30:m["cooldown"]=5.
        else:m["stable"]=None

    async def _supervise(self):
        while not self.closing:
            now=monotonic()
            for key in sorted(self.supervision):
                s=self.sessions[key];m=self.supervision[key];self._sample(key,now)
                if key not in self.desired or s.active() or s.stopping:continue
                if s.state=="error" and s.error=="invalid_source":continue
                if s.state in ("error","ended") and not m["next"]:
                    m["next"]=now+m["cooldown"];m["cooldown"]=min(60.,2*m["cooldown"])
                if now<m["next"]:continue
                if sum(v.active() for v in self.sessions.values())>=MAX_ACTIVE:continue
                if s.task is not None:m["restarts"]+=1
                s.start();m["next"]=0.
            await asyncio.sleep(.25)

    def gateway_status(self):
        now=monotonic();rows=[]
        for key,s in self.sessions.items():
            age=(now-s.arrivals[-1]) if s.arrivals else None
            fresh=s.state=="running" and age is not None and 0<=age<=5
            m=self.supervision.get(key)
            if m:self._sample(key,now)
            rows.append({"source_id":key,"intersection_code":s.spec.intersection_code,"kind":s.spec.kind,
                "continuous_opt_in":s.spec.continuous,"desired":key in self.desired,
                "capture_state":s.state,"observation":"recent_frames" if fresh else "unknown",
                "last_frame_age_seconds":round(age,3) if age is not None else None,
                "session_frames":s.frames,"process_observed_frames":m["total_frames"] if m else None,
                "supervisor_restarts":m["restarts"] if m else None,
                "retry_in_seconds":max(0,round(m["next"]-now,2)) if m and m["next"] and key in self.desired else None})
        return {"schema_version":1,"state":"running" if self.supervisor_task and not self.supervisor_task.done() else "idle",
            "max_active":MAX_ACTIVE,"sources":rows,"scope":"process_capture_only","availability_24h_validated":False,
            "physical_actuation":False,"operational_decision":"abstain"}

    def start(self,source_id):
        session = self.sessions[source_id]
        if self.closing or (not session.active() and sum(s.active() for s in self.sessions.values())>=MAX_ACTIVE):
            raise SourceBusy
        if source_id in self.supervision:self._sample(source_id,monotonic())
        session.start()
        if session.spec.continuous:
            self.desired.add(source_id)
            self.supervision[source_id]["next"]=0.
            self.start_supervisor()
        return session.status()

    async def stop(self,source_id):
        session = self.sessions[source_id]
        self.desired.discard(source_id)
        if source_id in self.supervision:
            self._sample(source_id,monotonic());self.supervision[source_id]["next"]=0.
        await session.stop()
        return session.status()

    async def shutdown(self):
        self.closing = True
        if self.supervisor_task:
            self.supervisor_task.cancel()
            await asyncio.gather(self.supervisor_task,return_exceptions=True)
            self.supervisor_task=None
        await asyncio.gather(*(s.stop() for s in self.sessions.values()))

    def take_latest(self,source_id):
        return self.sessions[source_id].take_latest()

    def status(self):
        sources = [s.status() for s in self.sessions.values()]
        states = {s["state"] for s in sources}
        state = ("not_configured" if not sources else "degraded" if "error" in states or "reconnecting" in states
                 else "running" if "running" in states else "starting" if "starting" in states else "idle")
        return {"state":state,"registered":len(sources),"active":sum(s.active() for s in self.sessions.values()),
                "max_active":MAX_ACTIVE,"sources":sources,"inference_connected":False}
