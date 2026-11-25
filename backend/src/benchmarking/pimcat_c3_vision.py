"""Offline pedestrian perception, never loaded by the operational pipeline."""
from dataclasses import dataclass
from math import hypot, isfinite
from pathlib import Path
import cv2
import numpy as np
from src.vision.yolo import preprocess_yolox, _yolox_grid
from src.vision.model_artifacts import YOLOX_S_SHA256
from src.validation.io import sha256_file


@dataclass(frozen=True)
class Person:
    box: tuple
    score: float
    def __post_init__(self):
        if len(self.box)!=4 or not all(isfinite(v) for v in self.box) or not 0<=self.box[0]<self.box[2]<=1 or not 0<=self.box[1]<self.box[3]<=1 or not 0<=self.score<=1:
            raise ValueError("invalid person observation")
    @property
    def foot(self):
        return ((self.box[0]+self.box[2])/2,self.box[3])


def iou(a,b):
    x,y,r,s=a;u,v,w,z=b
    inter=max(0,min(r,w)-max(x,u))*max(0,min(s,z)-max(y,v))
    return inter/((r-x)*(s-y)+(w-u)*(z-v)-inter)


def decode_people(output,geometry):
    raw=np.asarray(output,dtype=np.float32)
    if raw.shape!=(1,8400,85) or not np.isfinite(raw).all():
        raise ValueError("invalid YOLOX tensor")
    rows=raw[0].copy()
    if (rows[:,4:]<0).any() or (rows[:,4:]>1).any() or (np.abs(rows[:,2:4])>20).any():
        raise ValueError("invalid YOLOX scores or logits")
    grid,stride=_yolox_grid()
    rows[:,:2]=(rows[:,:2]+grid)*stride
    rows[:,2:4]=np.exp(rows[:,2:4])*stride
    scores=rows[:,4:5]*rows[:,5:]
    ids=scores.argmax(axis=1)
    indices=sorted(np.flatnonzero((ids==0)&(scores[:,0]>=.10)),key=lambda i:(-float(scores[i,0]),int(i)))
    ratio,w,h=geometry
    if not all(isfinite(v) and v>0 for v in geometry):raise ValueError("invalid geometry")
    kept=[]
    for i in indices[:300]:
        cx,cy,bw,bh=map(float,rows[i,:4])
        box=tuple(max(0,min(1,v)) for v in ((cx-bw/2)/ratio/w,(cy-bh/2)/ratio/h,(cx+bw/2)/ratio/w,(cy+bh/2)/ratio/h))
        if box[0]>=box[2] or box[1]>=box[3]:continue
        if not any(iou(box,d.box)>.45 for d in kept):
            kept.append(Person(box,float(scores[i,0])))
        if len(kept)==100:break
    return tuple(kept)


class PersonDetector:
    def __init__(self,path):
        path=Path(path)
        if not path.is_file() or not 0<path.stat().st_size<=64*1024*1024 or sha256_file(path)!=YOLOX_S_SHA256:
            raise ValueError("model identity mismatch")
        cv2.setNumThreads(1)
        self.net=cv2.dnn.readNetFromONNX(str(path))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.infer(np.zeros((64,64,3),dtype=np.uint8))
    def infer(self,image):
        blob,g=preprocess_yolox(image)
        self.net.setInput(blob)
        return decode_people(self.net.forward(),g)


@dataclass(frozen=True)
class Geometry:
    topology: str
    waiting: tuple
    crossing: tuple
    def __post_init__(self):
        if self.topology not in ("intersection","midblock") or not 1<=len(self.waiting)<=2:raise ValueError("invalid topology")
        zones=(*self.waiting,self.crossing)
        for i,z in enumerate(zones):
            Person(z,1)
            if any(iou(z,q)>0 for q in zones[:i]):raise ValueError("overlapping zones")
    def region(self,p):
        def inside(z):return z[0]<p[0]<z[2] and z[1]<p[1]<z[3]
        if inside(self.crossing):return "crossing"
        if any(inside(z) for z in self.waiting):return "waiting"
        return "outside"


@dataclass
class Track:
    observation: Person
    seen: float
    region: str
    since: float


class Perception:
    """Conservative short-lived association; no image storage or external identity."""
    def __init__(self,geometry=None):
        self.geometry=geometry
        self.tracks={}
        self.counter=0
        self.last=None
        self.oldest=None
        self.created=0
        self.expired=0
        self.ambiguous=0
    def update(self,t,people,*,available=True,occluded=False,button=False):
        if not isfinite(t) or t<0 or (self.last is not None and t<=self.last):raise ValueError("invalid source clock")
        gap=self.last is not None and t-self.last>1
        self.last=t
        if button and self.oldest is None:self.oldest=t
        for k in list(self.tracks):
            if t-self.tracks[k].seen>1:
                del self.tracks[k];self.expired+=1
        good=[p for p in people if p.score>=.25] if available and not occluded else []
        uncertain=not available or occluded or gap or any(p.score<.25 for p in people)
        # Unique mutual candidate only. Ambiguous detections start no new track.
        candidates={i:[k for k,q in self.tracks.items() if
            iou(p.box,q.observation.box)>=.2 or hypot(p.foot[0]-q.observation.foot[0],p.foot[1]-q.observation.foot[1])<=.045]
            for i,p in enumerate(good)}
        used=set();visible=[]
        for i,p in enumerate(good):
            matches=candidates[i]
            if matches and (len(matches)!=1 or sum(matches[0] in v for v in candidates.values())!=1):
                uncertain=True;self.ambiguous+=1;continue
            region=self.geometry.region(p.foot) if self.geometry else "unmapped"
            if matches:
                k=matches[0];old=self.tracks[k]
                since=old.since if old.region==region and t-old.seen<=.25 else t
            else:
                self.counter+=1;k=self.counter;self.created+=1;since=t
            self.tracks[k]=Track(p,t,region,since)
            used.add(k);visible.append(self.tracks[k])
        if set(self.tracks)-used:uncertain=True
        waiting=[q for q in visible if q.region=="waiting"]
        occupied=any(q.region=="crossing" for q in visible)
        if waiting:
            first=min(q.since for q in waiting)
            self.oldest=first if self.oldest is None else min(self.oldest,first)
        return {"waiting_observed":len(waiting) if self.geometry and available and not occluded else None,
            "demand":"possible" if waiting or self.oldest is not None else "unknown",
            "intention":"candidate" if any(t-q.since>=1 for q in waiting) else "unknown",
            "crossing":"occupied_observed" if occupied else "unknown",
            "oldest_observed_wait_seconds":None if self.oldest is None else t-self.oldest,
            "uncertain":bool(uncertain or not self.geometry),"visible_tracks":len(visible),
            "operational_decision":"abstain","physical_actuation":False}
    def acknowledge(self,*,independent_service_confirmed,waiting_area_confirmed_empty):
        # No caller in runtime. Requires external evidence; never invoked from camera observations.
        if independent_service_confirmed is not True or waiting_area_confirmed_empty is not True:
            raise ValueError("independent evidence required")
        self.oldest=None
