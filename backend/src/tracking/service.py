from collections import Counter
from src.tracking.tracker import ByteTrackInspired

class TrackingService:
    def __init__(self,vision):
        self.vision=vision
        self.trackers={}
        self.results={}
        self.errors={}
        self.processed=0
        self.failed=0
        self.analytics=None

    def consume(self,batch):
        source=batch.source_id
        try:
            if source not in self.vision.video.sessions:
                raise ValueError("unknown source")
            tracker=self.trackers.get(source)
            if tracker is None:
                low=self.vision.spec.confidence if self.vision.spec else .25
                tracker=self.trackers[source]=ByteTrackInspired(high=max(.6,low),low=low)
            self.results[source]=tracker.update(batch)
            self.errors.pop(source,None)
            self.processed+=1
        except Exception:
            self.results.pop(source,None)
            self.trackers.pop(source,None)
            if source in self.vision.video.sessions:
                self.errors[source]="tracking_failed"
            self.failed+=1
            return
        if self.analytics is not None:
            self.analytics.consume(self.results[source])

    def clear(self):
        self.trackers.clear()
        self.results.clear()
        self.errors.clear()
        if self.analytics is not None:
            self.analytics.clear()

    def latest(self,source_id):
        current=self.vision.valid_result(source_id)
        result=self.results.get(source_id)
        if self.vision.state!="ready" or current is None or result is None:
            return None
        if (current.session_id,current.frame_sequence,current.model_sha256)!=(result.session_id,result.frame_sequence,result.model_sha256):
            return None
        return result

    def status(self):
        sources=[]
        for source_id,session in self.vision.video.sessions.items():
            result=self.latest(source_id)
            if result is not None:
                confirmed=[t for t in result.tracks if t.state=="confirmed"]
                sources.append({"source_id":source_id,"intersection_code":result.intersection_code,
                    "frame_sequence":result.frame_sequence,"live":session.state=="running",
                    "confirmed_visible":len(confirmed),"tentative_visible":len(result.tracks)-len(confirmed),
                    "classes":dict(Counter(t.label for t in confirmed)),
                    "tracking_ms":result.tracking_ms,"skipped_frames":result.skipped_frames})
        return {"state":"not_loaded" if self.vision.state!="ready" else "degraded" if self.errors else "ready",
                "algorithm":"bytetrack_inspired_v1","processed":self.processed,"failed":self.failed,
                "sources":sources,"errors":dict(self.errors),"passage_counting":False}
