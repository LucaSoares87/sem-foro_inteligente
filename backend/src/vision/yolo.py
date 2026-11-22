import hashlib
import cv2
import numpy as np

from src.vision.contracts import CLASSES, MAX_DETECTIONS, MAX_MODEL_BYTES, Detection

SIZE=640
MAX_CANDIDATES=300
MAX_PREDICTIONS=8400

def preprocess(image):
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

def decode(output, geometry, confidence=.25, nms_iou=.45):
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
    def iou(a,b):
        ax,ay,ar,ab=a.xyxy; bx,by,br,bb=b.xyxy
        inter=max(0,min(ar,br)-max(ax,bx))*max(0,min(ab,bb)-max(ay,by))
        return inter/((ar-ax)*(ab-ay)+(br-bx)*(bb-by)-inter)
    kept=[]
    for det in candidates:
        if not any(det.label==old.label and iou(det,old)>nms_iou for old in kept):
            kept.append(det)
            if len(kept)==MAX_DETECTIONS:
                break
    return tuple(kept)

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
        # Load is confirmed only after a successful forward pass and output validation.
        self.infer(np.zeros((64,64,3),dtype=np.uint8))

    def infer(self,image):
        blob,geometry=preprocess(image)
        self.net.setInput(blob)
        return decode(self.net.forward(),geometry,self.spec.confidence,self.spec.nms_iou)
