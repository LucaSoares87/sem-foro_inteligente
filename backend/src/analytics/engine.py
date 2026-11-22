from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4
from src.analytics.contracts import LineMetric, RegionMetric, TrafficSnapshot
from src.analytics.geometry import contains, crosses_segment, foot, image_coverage, side

@dataclass
class Anchor:
    side: int
    point: tuple
    sequence: int
    timestamp: object

class TrafficEngine:
    def __init__(self,config):
        self.config=config
        self.geometry_hash=sha256(config.model_dump_json().encode()).hexdigest()
        self.reset()

    def reset(self):
        self.identity=None
        self.epoch=uuid4()
        self.last_sequence=0
        self.last_time=None
        self.started=None
        self.batches=self.skipped=self.discontinuities=0
        self.anchors={}
        self.counts={line.line_id:[0,0] for line in self.config.lines}

    def consume(self,batch):
        if (batch.source_id,batch.intersection_code)!=(self.config.source_id,self.config.intersection_code):
            raise ValueError("geometry source mismatch")
        identity=(batch.session_id,batch.tracking_epoch,batch.model_sha256,batch.purpose)
        if identity!=self.identity:
            self.reset()
            self.identity=identity
            self.started=batch.received_at
        elif batch.frame_sequence<=self.last_sequence:
            raise ValueError("out-of-order analytics batch")
        delta=batch.frame_sequence-self.last_sequence if self.last_sequence else 1
        dt=(batch.received_at-self.last_time).total_seconds() if self.last_time else 0
        if self.last_time and (dt<=0 or dt>self.config.max_gap_seconds or delta>self.config.max_gap_frames):
            self.anchors.clear()
            self.discontinuities+=1
        self.skipped+=max(0,delta-1)
        self.batches+=1
        confirmed=[t for t in batch.tracks if t.state=="confirmed"]
        if len({t.track_id for t in batch.tracks})!=len(batch.tracks):
            raise ValueError("duplicate track id")
        visible={t.track_id for t in confirmed}
        self.anchors={k:v for k,v in self.anchors.items() if k[1] in visible}
        for line in self.config.lines:
            for track in confirmed:
                key=(line.line_id,track.track_id)
                point=foot(track.xyxy)
                current_side=side(line,point)
                anchor=self.anchors.get(key)
                if anchor and (batch.frame_sequence-anchor.sequence>self.config.max_gap_frames or
                               (batch.received_at-anchor.timestamp).total_seconds()>self.config.max_gap_seconds):
                    self.anchors.pop(key,None)
                    anchor=None
                if current_side==0:
                    continue
                if anchor and anchor.side!=current_side and crosses_segment(line,anchor.point,point):
                    self.counts[line.line_id][0 if current_side==1 else 1]+=1
                self.anchors[key]=Anchor(current_side,point,batch.frame_sequence,batch.received_at)
        regions=tuple(RegionMetric(region_id=r.region_id,
            confirmed_visible=sum(contains(r.xyxy,foot(t.xyxy)) for t in confirmed),
            image_coverage_pct=image_coverage(r.xyxy,[t.xyxy for t in confirmed])) for r in self.config.regions)
        lines=tuple(LineMetric(line_id=line.line_id,negative_to_positive=self.counts[line.line_id][0],
                               positive_to_negative=self.counts[line.line_id][1]) for line in self.config.lines)
        self.last_sequence,self.last_time=batch.frame_sequence,batch.received_at
        quality=("initializing" if self.batches==1 else "limited_sampling" if self.skipped or self.discontinuities or
                 batch.lost_private or len(confirmed)!=len(batch.tracks) else "experimental")
        return TrafficSnapshot(source_id=batch.source_id,intersection_code=batch.intersection_code,
            session_id=batch.session_id,tracking_epoch=batch.tracking_epoch,analytics_epoch=self.epoch,
            geometry_sha256=self.geometry_hash,model_sha256=batch.model_sha256,purpose=batch.purpose,
            frame_sequence=batch.frame_sequence,received_at=batch.received_at,window_started_at=self.started,
            observed_batches=self.batches,skipped_frames=self.skipped,discontinuities=self.discontinuities,
            tentative_visible=len(batch.tracks)-len(confirmed),lost_private=batch.lost_private,
            quality=quality,regions=regions,lines=lines)
