from dataclasses import dataclass
from time import monotonic
from uuid import uuid4
import numpy as np
from src.tracking.association import associate
from src.tracking.contracts import TrackBatch, TrackObservation

MAX_TRACKS=200
MAX_GAP_FRAMES=30
MAX_GAP_SECONDS=2.0

def measure(box):
    x1,y1,x2,y2=box
    return np.array([(x1+x2)/2,(y1+y2)/2,x2-x1,y2-y1],dtype=float)

@dataclass
class Track:
    track_id: int
    label: str
    mean: np.ndarray
    covariance: np.ndarray
    hits: int
    last_sequence: int
    last_time: object
    observed: bool=True
    confidence: float=0
    box: tuple=(0,0,1,1)

    @classmethod
    def create(cls,track_id,det,batch):
        return cls(track_id,det.label,np.r_[measure(det.xyxy),np.zeros(4)],
                   np.eye(8)*.01,1,batch.frame_sequence,batch.received_at,
                   True,det.confidence,det.xyxy)

    def predict(self,dt):
        transition=np.eye(8)
        transition[:4,4:]=np.eye(4)*dt
        self.mean=transition@self.mean
        self.covariance=transition@self.covariance@transition.T+np.eye(8)*.0001
        self.observed=False

    def predicted_box(self):
        x,y,w,h=self.mean[:4]
        w,h=max(.001,w),max(.001,h)
        return (max(0,x-w/2),max(0,y-h/2),min(1,x+w/2),min(1,y+h/2))

    def update(self,det,batch):
        h=np.eye(8)[:4]
        noise=np.eye(4)*.001
        gain=np.linalg.solve(h@self.covariance@h.T+noise,h@self.covariance).T
        self.mean=self.mean+gain@(measure(det.xyxy)-h@self.mean)
        residual=np.eye(8)-gain@h
        self.covariance=residual@self.covariance@residual.T+gain@noise@gain.T
        self.hits+=1
        self.last_sequence,self.last_time=batch.frame_sequence,batch.received_at
        self.observed=True
        self.confidence,self.box=det.confidence,det.xyxy

class ByteTrackInspired:
    """Two-confidence-pass association with motion prediction, no appearance embeddings."""
    def __init__(self,high=.6,low=.25):
        if not 0<low<=high<=1:
            raise ValueError("invalid tracking confidence thresholds")
        self.high,self.low=high,low
        self.reset()

    def reset(self):
        self.epoch=uuid4()
        self.session=None
        self.source=None
        self.model=None
        self.last_sequence=0
        self.last_time=None
        self.next_id=1
        self.tracks=[]

    def update(self,batch):
        started=monotonic()
        identity=(batch.source_id,batch.intersection_code,batch.session_id,batch.model_sha256,batch.purpose)
        if self.session!=identity:
            self.reset()
            self.session=identity
        if batch.frame_sequence<=self.last_sequence:
            raise ValueError("nonmonotonic frame sequence")
        gap=batch.frame_sequence-self.last_sequence if self.last_sequence else 1
        dt=(batch.received_at-self.last_time).total_seconds() if self.last_time else 0
        if self.last_time and (dt<0 or dt>MAX_GAP_SECONDS or gap>MAX_GAP_FRAMES):
            self.reset()
            self.session=identity
            dt=0
        self.tracks=[t for t in self.tracks if batch.frame_sequence-t.last_sequence<=MAX_GAP_FRAMES
                     and 0<=(batch.received_at-t.last_time).total_seconds()<=MAX_GAP_SECONDS]
        previously_observed={t.track_id for t in self.tracks if t.observed}
        for track in self.tracks:
            track.predict(dt)
        high=[d for d in batch.detections if d.confidence>=self.high]
        low=[d for d in batch.detections if self.low<=d.confidence<self.high]
        pairs,missed,new=associate(self.tracks,high,.30)
        for i,j in pairs:
            self.tracks[i].update(high[j],batch)
        candidates=[self.tracks[i] for i in missed
                    if self.tracks[i].hits>=2 and self.tracks[i].track_id in previously_observed]
        pairs,_,_=associate(candidates,low,.20)
        for i,j in pairs:
            candidates[i].update(low[j],batch)
        self.tracks=[t for t in self.tracks if t.observed or t.hits>=2]
        for j in new:
            if len(self.tracks)>=MAX_TRACKS:
                break
            self.tracks.append(Track.create(self.next_id,high[j],batch))
            self.next_id+=1
        self.last_sequence,self.last_time=batch.frame_sequence,batch.received_at
        observed=tuple(TrackObservation(track_id=t.track_id,label=t.label,
                     state="confirmed" if t.hits>=2 else "tentative",
                     confidence=t.confidence,xyxy=t.box,hits=t.hits)
                     for t in self.tracks if t.observed)
        return TrackBatch(source_id=batch.source_id,intersection_code=batch.intersection_code,
            session_id=batch.session_id,tracking_epoch=self.epoch,frame_sequence=batch.frame_sequence,
            received_at=batch.received_at,model_sha256=batch.model_sha256,purpose=batch.purpose,
            tracking_ms=(monotonic()-started)*1000,skipped_frames=max(0,gap-1),
            lost_private=sum(not t.observed for t in self.tracks),tracks=observed)
