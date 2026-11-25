"""Offline research-only clip preparation. Does not modify the source or runtime."""
import argparse
import hashlib
import json
import math
from datetime import timedelta
from pathlib import Path

import cv2

from src.benchmarking.bellevue import _recorded_at
from src.validation.io import sha256_file

FPS = 30
STEP = 1 / FPS
TOLERANCE = .002
SOURCE_SHA = "f53d6b706080e0d9bb587e9d254e57a3539ae22f04e54ce503f1572e894cc4a5"
SOURCE_NAME = "Bellevue_116th_NE12th__2017-09-11_12-08-33.mp4"


def select_span(timestamps, frame_count):
    """First span with real consecutive frames, bounded cadence and total drift."""
    if frame_count < 2:
        raise ValueError("at least two frames required")
    start = 0
    for i, stamp in enumerate(timestamps):
        if not math.isfinite(stamp) or stamp < 0:
            raise ValueError("invalid source timestamp")
        if i and (abs(stamp - timestamps[i-1] - STEP) > TOLERANCE
                  or abs(stamp - timestamps[start] - (i-start)*STEP) > TOLERANCE):
            start = i
        if i-start+1 == frame_count:
            return start, i+1
    raise ValueError("no continuous 30 FPS span of requested length")


def prepare(source, output, seconds=32, *, source_name=SOURCE_NAME, source_sha=SOURCE_SHA):
    source, output = Path(source), Path(output)
    if source.name != source_name or sha256_file(source) != source_sha:
        raise ValueError("source identity or sha256 mismatch")
    if output.suffix != ".mkv" or output.resolve() == source.resolve() or output.exists():
        raise ValueError("new MKV output required; no overwrite")
    if not 1 <= seconds <= 108:
        raise ValueError("preliminary clip must be 1..108 seconds")
    stamps = []
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError("source not decodable")
        while capture.grab():
            stamps.append(capture.get(cv2.CAP_PROP_POS_MSEC)/1000)
    finally:
        capture.release()
    start, end = select_span(stamps, seconds*FPS)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.stem + ".part.mkv")
    if temp.exists():
        raise ValueError("partial output already exists")
    capture = cv2.VideoCapture(str(source))
    writer = None
    source_pixels = hashlib.sha256()
    try:
        for i in range(end):
            ok, frame = capture.read()
            if not ok or frame is None or frame.shape != (720,1280,3):
                raise ValueError("source decode or resolution mismatch")
            if i < start:
                continue
            stamp = capture.get(cv2.CAP_PROP_POS_MSEC)/1000
            if abs(stamp-stamps[i]) > .0001:
                raise ValueError("source timestamp changed on second decode")
            if writer is None:
                writer = cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*"FFV1"),FPS,(1280,720))
                if not writer.isOpened():
                    raise ValueError("lossless FFV1 encoder unavailable")
            source_pixels.update(frame.tobytes())
            writer.write(frame)
        writer.release()
        writer = None
        check = cv2.VideoCapture(str(temp))
        decoded_pixels = hashlib.sha256()
        decoded = 0
        try:
            if not check.isOpened() or abs(check.get(cv2.CAP_PROP_FPS)-FPS) > .001:
                raise ValueError("derived clip is not exact nominal 30 FPS")
            while True:
                ok, frame = check.read()
                if not ok:
                    break
                if frame.shape != (720,1280,3):
                    raise ValueError("derived resolution mismatch")
                stamp=check.get(cv2.CAP_PROP_POS_MSEC)/1000
                if abs(stamp-decoded*STEP) > TOLERANCE:
                    raise ValueError("derived clip timestamp mismatch")
                decoded_pixels.update(frame.tobytes())
                decoded += 1
        finally:
            check.release()
        if decoded != end-start or source_pixels.digest()!=decoded_pixels.digest():
            raise ValueError("lossless one-to-one pixel verification failed")
        temp.replace(output)
    except Exception:
        if writer is not None:
            writer.release()
        temp.unlink(missing_ok=True)
        raise
    finally:
        capture.release()
    return {
        "schema_version":1,"origin":"external_real_replay","commercial_demo_authorized":False,
        "source_filename":source.name,"source_sha256":source_sha,
        "derived_filename":output.name,"derived_sha256":sha256_file(output),
        "source_start_frame_zero_based":start,"source_end_frame_exclusive":end,
        "source_start_seconds":stamps[start],"source_end_seconds":stamps[end-1],
        "recorded_at":(_recorded_at(source)+timedelta(seconds=stamps[start])).isoformat(),
        "frames":end-start,"fps":FPS,"duration_seconds":seconds,
        "source_max_cadence_error_seconds":max(abs(stamps[i]-stamps[i-1]-STEP) for i in range(start+1,end)),
        "source_max_drift_seconds":max(abs(stamps[i]-stamps[start]-(i-start)*STEP) for i in range(start,end)),
        "decoded_pixel_sha256":source_pixels.hexdigest(),
        "interpolated_frames":0,"duplicated_frames":0,"dropped_frames_inside_span":0,
        "physical_actuation":False,"operationally_validated":False,
        "scope":"preliminary_timebase_normalized_research"
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--evidence",required=True)
    p.add_argument("--seconds",type=int,default=32)
    a=p.parse_args()
    evidence=Path(a.evidence)
    if evidence.exists() or evidence.resolve() in {Path(a.source).resolve(),Path(a.output).resolve()}:
        raise ValueError("new distinct evidence output required")
    result=prepare(a.source,a.output,a.seconds)
    evidence.parent.mkdir(parents=True,exist_ok=True)
    with evidence.open("x",encoding="utf-8") as handle:
        json.dump(result,handle,indent=2,sort_keys=True)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
