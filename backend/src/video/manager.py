import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import monotonic, monotonic_ns

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
                    self.frames,width,height,now,self.last_delay_ms,jpeg)
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
                "kind":self.spec.kind,"state":self.state,"error_code":self.error,
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

    def start(self,source_id):
        session = self.sessions[source_id]
        if self.closing or (not session.active() and sum(s.active() for s in self.sessions.values())>=MAX_ACTIVE):
            raise SourceBusy
        session.start()
        return session.status()

    async def stop(self,source_id):
        session = self.sessions[source_id]
        await session.stop()
        return session.status()

    async def shutdown(self):
        self.closing = True
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
