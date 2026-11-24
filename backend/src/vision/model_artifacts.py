import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from src.vision.contracts import ModelSpec

YOLOX_S_URL="https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"
YOLOX_S_SHA256="c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
YOLOX_S_PROVENANCE="Megvii-BaseDetection/YOLOX release 0.1.1rc0 official yolox_s.onnx"
YOLOX_S_LICENSE="Apache-2.0 https://github.com/Megvii-BaseDetection/YOLOX/blob/main/LICENSE"
MAX_FETCH_BYTES=64*1024*1024


def fetch_yolox_s(output,opener=urlopen,expected_sha256=YOLOX_S_SHA256):
    output=Path(output)
    if output.suffix.lower()!=".onnx":
        raise ValueError("model output must be .onnx")
    output.parent.mkdir(parents=True,exist_ok=True)
    part=output.with_name(output.name+".part")
    part.unlink(missing_ok=True)
    request=Request(YOLOX_S_URL,headers={"User-Agent":"semaforo-inteligente-model-fetch/1"})
    digest=hashlib.sha256()
    total=0
    try:
        with opener(request,timeout=90) as response, part.open("wb") as handle:
            declared=response.headers.get("Content-Length")
            if declared is not None and int(declared)>MAX_FETCH_BYTES:
                raise ValueError("model artifact too large")
            while True:
                chunk=response.read(1024*1024)
                if not chunk:
                    break
                total+=len(chunk)
                if total>MAX_FETCH_BYTES:
                    raise ValueError("model artifact too large")
                digest.update(chunk)
                handle.write(chunk)
        if total==0 or digest.hexdigest()!=expected_sha256:
            raise ValueError("model hash mismatch")
        os.replace(part,output)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return ModelSpec(filename=output.name,sha256=expected_sha256,
        provenance=YOLOX_S_PROVENANCE,license_ref=YOLOX_S_LICENSE,
        architecture="yolox",purpose="validation_only",confidence=.25,nms_iou=.45)


def main(argv=None):
    parser=argparse.ArgumentParser("fetch pinned YOLOX-S model")
    parser.add_argument("--output",required=True)
    parser.add_argument("--spec-output")
    args=parser.parse_args(argv)
    spec=fetch_yolox_s(args.output)
    if args.spec_output:
        target=Path(args.spec_output)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(spec.model_dump(mode="json"),indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(spec.model_dump(mode="json"),sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
