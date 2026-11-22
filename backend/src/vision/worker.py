"""Local inference subprocess, no image persistence or model downloads."""
import json
import struct
import sys
from time import monotonic

from src.video.contracts import MAX_JPEG, MAX_WIDTH, MAX_HEIGHT
from src.vision.contracts import ModelSpec

LENGTH=struct.Struct("!I")

def reply(value):
    sys.stdout.buffer.write(json.dumps(value,allow_nan=False,separators=(",",":")).encode()+b"\n")
    sys.stdout.buffer.flush()

def main():
    import cv2
    import numpy as np
    from src.vision.yolo import YoloDetector
    try:
        init=json.loads(sys.stdin.buffer.readline(8192))
        spec=ModelSpec.model_validate(init["spec"])
        model=YoloDetector(spec.resolve(init["root"]),spec)
        reply({"state":"ready"})
    except Exception:
        reply({"state":"error","code":"model_load_failed"})
        return 2
    while True:
        header=sys.stdin.buffer.read(LENGTH.size)
        if not header:
            return 0
        try:
            size=LENGTH.unpack(header)[0]
            if not 0<size<=MAX_JPEG:
                return 3
            data=sys.stdin.buffer.read(size)
            if len(data)!=size:
                return 3
            start=monotonic()
            image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
            if image is None or not (0<image.shape[0]<=MAX_HEIGHT and 0<image.shape[1]<=MAX_WIDTH):
                raise ValueError("invalid image")
            detections=model.infer(image)
            reply({"state":"ok","inference_ms":(monotonic()-start)*1000,
                   "detections":[item.model_dump(mode="json") for item in detections]})
        except Exception:
            reply({"state":"error","code":"inference_failed"})
            return 4

if __name__=="__main__":
    sys.exit(main())
