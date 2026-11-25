"""Isolated decoder. No original frames are written to disk."""
import json
import math
import sys
import time

from src.video.contracts import MAX_WIDTH, MAX_HEIGHT, MAX_JPEG
from src.video.protocol import HEADER

def run(config):
    import cv2
    cv2.setNumThreads(1)
    kind, locator = config["kind"], config["locator"]
    capture = cv2.VideoCapture()
    try:
        if kind == "rtsp":
            opened = capture.open(locator,cv2.CAP_FFMPEG,[
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,4000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,4000])
        else:
            opened = capture.open(locator)
        if not opened:
            return 2
        source_fps = capture.get(cv2.CAP_PROP_FPS)
        fps = config["fps"]
        if kind == "file" and math.isfinite(source_fps) and source_fps>0:
            fps = min(fps, source_fps)
        if kind != "file":
            capture.set(cv2.CAP_PROP_BUFFERSIZE,1)
        sequence = 0
        # RTSP must drain the source at its native cadence. Limit emitted JPEGs,
        # not reads: sleeping between reads accumulates stale decoded frames.
        next_emit_ns = None
        period_ns = max(1, round(1_000_000_000 / fps))
        while True:
            start = time.monotonic()
            ok, frame = capture.read()
            timestamp = time.monotonic_ns()
            if not ok or frame is None:
                if kind == "file" and sequence:
                    return 0
                return 3
            height,width = frame.shape[:2]
            if not width or not height:
                return 3
            if kind == "rtsp":
                if next_emit_ns is not None and timestamp < next_emit_ns:
                    continue
                # Never replay missed emission slots as a burst.
                next_emit_ns = timestamp + period_ns
            scale = min(1,MAX_WIDTH/width,MAX_HEIGHT/height)
            if scale<1:
                frame = cv2.resize(frame,(max(1,int(width*scale)),max(1,int(height*scale))),interpolation=cv2.INTER_AREA)
            height,width = frame.shape[:2]
            ok, encoded = cv2.imencode(".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,80])
            if not ok or encoded.nbytes>MAX_JPEG:
                return 4
            sequence += 1
            sys.stdout.buffer.write(HEADER.pack(width,height,sequence,timestamp,encoded.nbytes))
            sys.stdout.buffer.write(encoded.tobytes())
            sys.stdout.buffer.flush()
            if kind != "rtsp":
                time.sleep(max(0,1/fps-(time.monotonic()-start)))
    finally:
        capture.release()

def main():
    try:
        config = json.loads(sys.stdin.buffer.read(8192))
        return run(config)
    except (Exception, KeyboardInterrupt):
        return 4

if __name__ == "__main__":
    sys.exit(main())
