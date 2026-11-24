import hashlib
import json
from pathlib import Path
import cv2
from src.validation.contracts import DatasetManifest

MAX_JSON_BYTES=64*1024*1024

def sha256_file(path):
    digest=hashlib.sha256()
    with open(path,"rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_json_model(path,model):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_JSON_BYTES:
        raise ValueError("invalid json artifact")
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,UnicodeError):
        raise ValueError("invalid json artifact") from None

def verify_video(manifest: DatasetManifest,path,capture_factory=cv2.VideoCapture):
    path=Path(path)
    if not path.is_file() or path.name!=manifest.video_filename:
        raise ValueError("video artifact mismatch")
    if sha256_file(path)!=manifest.video_sha256:
        raise ValueError("video sha256 mismatch")
    capture=capture_factory(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("video not decodable")
        width=int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height=int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        fps=float(capture.get(cv2.CAP_PROP_FPS))
        frame_count=int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    finally:
        capture.release()
    if width!=manifest.width or height!=manifest.height:
        raise ValueError("video resolution mismatch")
    if fps<=0 or abs(fps-manifest.fps)>max(.5,manifest.fps*.02):
        raise ValueError("video fps mismatch")
    if frame_count>0 and abs(frame_count-manifest.frame_count)>2:
        raise ValueError("video frame count mismatch")
    return {
        "sha256":manifest.video_sha256,"width":width,"height":height,
        "fps":fps,"frame_count":frame_count,"decoder":"opencv"
    }

def canonical_json(value):
    return json.dumps(value,separators=(",",":"),sort_keys=True,ensure_ascii=False)+"\n"
