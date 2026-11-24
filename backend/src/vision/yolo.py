import hashlib
from functools import lru_cache

import cv2
import numpy as np

from src.vision.contracts import CLASSES, MAX_DETECTIONS, MAX_MODEL_BYTES, Detection

SIZE=640
MAX_CANDIDATES=300
MAX_PREDICTIONS=8400


def preprocess_ultralytics(image):
    h,w=image.shape[:2]
    if h<=0 or w<=0:
        raise ValueError("invalid image")
    scale=min(SIZE/w,SIZE/h)
    nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
    left,top=(SIZE-nw)//2,(SIZE-nh)//2
    canvas=np.full((SIZE,SIZE,3),114,dtype=np.uint8)
    canvas[top:top+nh,left:left+nw]=cv2.resize(image,(nw,nh))
    blob=cv2.dnn.blobFromImage(canvas,1/255,(SIZE,SIZE),swapRB=True,crop=False)
    return blob,(nw/w,nh/h,left,top,w,h)


def preprocess_yolox(image):
    h,w=image.shape[:2]
    if h<=0 or w<=0:
        raise ValueError("invalid image")
    ratio=min(SIZE/h,SIZE/w)
    nw,nh=max(1,int(w*ratio)),max(1,int(h*ratio))
    canvas=np.full((SIZE,SIZE,3),114,dtype=np.uint8)
    canvas[:nh,:nw]=cv2.resize(image,(nw,nh),interpolation=cv2.INTER_LINEAR)
    blob=np.ascontiguousarray(canvas.transpose(2,0,1),dtype=np.float32)[None]
    return blob,(ratio,w,h)


def _iou(a,b):
    ax,ay,ar,ab=a.xyxy
    bx,by,br,bb=b.xyxy
    inter=max(0,min(ar,br)-max(ax,bx))*max(0,min(ab,bb)-max(ay,by))
    union=(ar-ax)*(ab-ay)+(br-bx)*(bb-by)-inter
    return inter/union if union>0 else 0.0


def _nms(candidates,nms_iou):
    kept=[]
    for det in sorted(candidates,key=lambda item:-item.confidence):
        if not any(det.label==old.label and _iou(det,old)>nms_iou for old in kept):
            kept.append(det)
            if len(kept)==MAX_DETECTIONS:
                break
    return tuple(kept)


def decode_ultralytics(output,geometry,confidence=.25,nms_iou=.45):
    raw=np.asarray(output)
    if raw.ndim!=3 or raw.shape[:2]!=(1,84) or not 1<=raw.shape[2]<=MAX_PREDICTIONS:
        raise ValueError("unsupported YOLO output")
    rows=raw[0].T
    if not np.isfinite(rows).all() or (rows[:,4:]<0).any() or (rows[:,4:]>1).any():
        raise ValueError("invalid YOLO scores")
    sx,sy,left,top,w,h=geometry
    ids=rows[:,4:].argmax(axis=1)
    scores=rows[np.arange(len(rows)),ids+4]
    valid=[i for i in range(len(rows)) if int(ids[i]) in CLASSES and scores[i]>=confidence]
    valid=sorted(valid,key=lambda i:(-float(scores[i]),i))[:MAX_CANDIDATES]
    candidates=[]
    for i in valid:
        cx,cy,bw,bh=map(float,rows[i,:4])
        if bw<=0 or bh<=0:
            continue
        x1=max(0,min(1,((cx-bw/2-left)/sx)/w))
        y1=max(0,min(1,((cy-bh/2-top)/sy)/h))
        x2=max(0,min(1,((cx+bw/2-left)/sx)/w))
        y2=max(0,min(1,((cy+bh/2-top)/sy)/h))
        if x1<x2 and y1<y2:
            candidates.append(Detection(label=CLASSES[int(ids[i])],confidence=float(scores[i]),xyxy=(x1,y1,x2,y2)))
    return _nms(candidates,nms_iou)


@lru_cache(maxsize=1)
def _yolox_grid():
    grids=[]
    strides=[]
    for stride in (8,16,32):
        hsize=wsize=SIZE//stride
        xv,yv=np.meshgrid(np.arange(wsize,dtype=np.float32),np.arange(hsize,dtype=np.float32))
        grid=np.stack((xv,yv),axis=2).reshape(-1,2)
        grids.append(grid)
        strides.append(np.full((len(grid),1),stride,dtype=np.float32))
    grid=np.concatenate(grids,axis=0)
    stride=np.concatenate(strides,axis=0)
    if grid.shape!=(MAX_PREDICTIONS,2) or stride.shape!=(MAX_PREDICTIONS,1):
        raise RuntimeError("invalid YOLOX grid")
    return grid,stride


def decode_yolox(output,geometry,confidence=.25,nms_iou=.45):
    raw=np.asarray(output,dtype=np.float32)
    if raw.shape!=(1,MAX_PREDICTIONS,85):
        raise ValueError("unsupported YOLOX output")
    if not np.isfinite(raw).all():
        raise ValueError("invalid YOLOX output")
    rows=raw[0].copy()
    scores_part=rows[:,4:]
    if (scores_part<0).any() or (scores_part>1).any():
        raise ValueError("invalid YOLOX scores")
    if (np.abs(rows[:,2:4])>20).any():
        raise ValueError("invalid YOLOX box logits")
    grid,stride=_yolox_grid()
    rows[:,:2]=(rows[:,:2]+grid)*stride
    rows[:,2:4]=np.exp(rows[:,2:4])*stride
    class_scores=rows[:,4:5]*rows[:,5:]
    ids=class_scores.argmax(axis=1)
    scores=class_scores[np.arange(len(rows)),ids]
    valid=[i for i in range(len(rows)) if int(ids[i]) in CLASSES and scores[i]>=confidence]
    valid=sorted(valid,key=lambda i:(-float(scores[i]),i))[:MAX_CANDIDATES]
    ratio,w,h=geometry
    candidates=[]
    for i in valid:
        cx,cy,bw,bh=map(float,rows[i,:4])
        if bw<=0 or bh<=0:
            continue
        x1=max(0,min(1,((cx-bw/2)/ratio)/w))
        y1=max(0,min(1,((cy-bh/2)/ratio)/h))
        x2=max(0,min(1,((cx+bw/2)/ratio)/w))
        y2=max(0,min(1,((cy+bh/2)/ratio)/h))
        if x1<x2 and y1<y2:
            candidates.append(Detection(label=CLASSES[int(ids[i])],confidence=float(scores[i]),xyxy=(x1,y1,x2,y2)))
    return _nms(candidates,nms_iou)


# Backward-compatible exports for the original model contract.
preprocess=preprocess_ultralytics
decode=decode_ultralytics


class YoloDetector:
    def __init__(self,path,spec):
        with open(path,"rb") as model:
            data=model.read(MAX_MODEL_BYTES+1)
        if not data or len(data)>MAX_MODEL_BYTES or hashlib.sha256(data).hexdigest()!=spec.sha256:
            raise ValueError("model hash mismatch")
        self.spec=spec
        cv2.setNumThreads(1)
        self.net=cv2.dnn.readNetFromONNX(np.frombuffer(data,dtype=np.uint8))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        # Load is confirmed only after a successful forward pass and family-specific output validation.
        self.infer(np.zeros((64,64,3),dtype=np.uint8))

    def infer(self,image):
        if self.spec.architecture=="yolox":
            blob,geometry=preprocess_yolox(image)
            decoder=decode_yolox
        else:
            blob,geometry=preprocess_ultralytics(image)
            decoder=decode_ultralytics
        self.net.setInput(blob)
        return decoder(self.net.forward(),geometry,self.spec.confidence,self.spec.nms_iou)
