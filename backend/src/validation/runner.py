from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import cv2
from src.analytics.engine import TrafficEngine
from src.tracking.tracker import ByteTrackInspired
from src.validation.contracts import CountValue,PredictedDetection,PredictedTrack,Predictions
from src.validation.io import verify_video
from src.vision.contracts import DetectionBatch
from src.vision.service import InferenceWorker

async def run_case(manifest,video_path,spec,model_root,geometry,
                   worker_factory=InferenceWorker,capture_factory=cv2.VideoCapture,verify=verify_video):
    verify(manifest,video_path)
    if (geometry.source_id,geometry.intersection_code)!=(manifest.source_id,manifest.intersection_code):
        raise ValueError("geometry/manifest mismatch")
    if manifest.origin=="field" and spec.purpose!="authorized_candidate":
        raise ValueError("field validation requires authorized candidate model")
    capture=capture_factory(str(Path(video_path)))
    if not capture.isOpened():
        raise ValueError("video not decodable")
    worker=worker_factory(spec,model_root)
    tracker=ByteTrackInspired(high=max(.6,spec.confidence),low=spec.confidence)
    traffic=TrafficEngine(geometry)
    session_id=uuid4()
    detections=[]
    tracks=[]
    last_snapshot=None
    sequence=0
    await worker.open()
    try:
        while sequence<manifest.frame_count:
            ok,frame=capture.read()
            if not ok or frame is None:
                raise ValueError("video ended before manifest frame count")
            sequence+=1
            if frame.shape[1]!=manifest.width or frame.shape[0]!=manifest.height:
                raise ValueError("frame resolution drift")
            encoded,jpeg=cv2.imencode(".jpg",frame,[int(cv2.IMWRITE_JPEG_QUALITY),90])
            if not encoded:
                raise ValueError("frame jpeg encoding failed")
            raw=jpeg.tobytes()
            result=await worker.infer(raw)
            received=manifest.recorded_at+timedelta(seconds=(sequence-1)/manifest.fps)
            batch=DetectionBatch(
                source_id=manifest.source_id,intersection_code=manifest.intersection_code,
                session_id=session_id,frame_sequence=sequence,received_at=received,
                inferred_at=datetime.now(timezone.utc),model_sha256=spec.sha256,purpose=spec.purpose,
                inference_ms=result["inference_ms"],detections=result["detections"])
            detections.extend(PredictedDetection(frame_sequence=sequence,label=item.label,
                confidence=item.confidence,xyxy=item.xyxy) for item in batch.detections)
            tracked=tracker.update(batch)
            tracks.extend(PredictedTrack(frame_sequence=sequence,track_id=item.track_id,
                label=item.label,confidence=item.confidence,xyxy=item.xyxy)
                for item in tracked.tracks if item.state=="confirmed")
            last_snapshot=traffic.consume(tracked)
        ok,extra=capture.read()
        if ok and extra is not None:
            raise ValueError("video contains more frames than manifest")
    finally:
        capture.release()
        await worker.close()
    counts=[]
    if last_snapshot is not None:
        for line in last_snapshot.lines:
            counts.append(CountValue(line_id=line.line_id,direction="negative_to_positive",
                                     label=None,count=line.negative_to_positive))
            counts.append(CountValue(line_id=line.line_id,direction="positive_to_negative",
                                     label=None,count=line.positive_to_negative))
    return Predictions(dataset_id=manifest.dataset_id,model_sha256=spec.sha256,
                       geometry_sha256=traffic.geometry_hash,detections=tuple(detections),
                       tracks=tuple(tracks),counts=tuple(counts))
