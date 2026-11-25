"""Offline planar calibration research. No camera/controller integration."""
import argparse
import json
from pathlib import Path
import math
import numpy as np
import cv2
from src.archive.store import fingerprint

FPS=(30,15,10,5)
SPEEDS=(2.,5.,10.)

def points(value,minimum):
    p=np.asarray(value,dtype=float)
    if p.ndim!=2 or p.shape[1]!=2 or len(p)<minimum or not np.isfinite(p).all():
        raise ValueError("invalid point set")
    if len(np.unique(p,axis=0))!=len(p):
        raise ValueError("duplicate points")
    return p

def normalize(p):
    center=p.mean(axis=0)
    centered=p-center
    radius=np.sqrt(np.mean(np.sum(centered**2,axis=1)))
    if not np.isfinite(radius) or radius<=1e-12:
        raise ValueError("degenerate coordinates")
    scale=np.sqrt(2)/radius
    T=np.array([[scale,0,-scale*center[0]],[0,scale,-scale*center[1]],[0,0,1.]])
    return centered*scale,T

def project(H,p):
    p=np.asarray(p,dtype=float)
    if p.shape!=(2,) or not np.isfinite(p).all():
        raise ValueError("invalid location")
    q=H@np.r_[p,1.]
    if not np.isfinite(q).all() or abs(q[2])<=1e-10*max(1.,np.linalg.norm(q)):
        raise ValueError("invalid projective denominator")
    return q[:2]/q[2]

class Calibration:
    def __init__(self,pixels,meters,check_pixels,check_meters):
        x,y=points(pixels,4),points(meters,4)
        u,v=points(check_pixels,2),points(check_meters,2)
        if len(x)!=len(y) or len(u)!=len(v):
            raise ValueError("unpaired points")
        if any(np.linalg.norm(a-b)<=1e-9 for a in x for b in u) or any(np.linalg.norm(a-b)<=1e-9 for a in y for b in v):
            raise ValueError("verification points overlap fit")
        X,Tx=normalize(x); Y,Ty=normalize(y)
        A=[]
        for (a,b),(s,t) in zip(X,Y):
            A.extend([[-a,-b,-1,0,0,0,s*a,s*b,s],[0,0,0,-a,-b,-1,t*a,t*b,t]])
        A=np.asarray(A)
        _,sigma,Vh=np.linalg.svd(A,full_matrices=True)
        if len(sigma)<8 or sigma[7]<=sigma[0]*1e-10:
            raise ValueError("degenerate DLT")
        H=np.linalg.inv(Ty)@Vh[-1].reshape(3,3)@Tx
        norm=np.linalg.norm(H)
        if not np.isfinite(H).all() or norm<=0:
            raise ValueError("invalid homography")
        self.H=H/norm
        if np.linalg.matrix_rank(self.H)<3:
            raise ValueError("singular homography")
        self.hull=cv2.convexHull(x.astype(np.float32))
        if cv2.contourArea(self.hull)<=1e-8:
            raise ValueError("degenerate hull")
        errs=np.array([np.linalg.norm(self.position(a)-b) for a,b in zip(u,v)])
        self.check_rms_m=float(np.sqrt(np.mean(errs**2)))
        self.check_max_m=float(errs.max())
    def position(self,p):
        a=np.asarray(p,dtype=float)
        if a.shape!=(2,) or not np.isfinite(a).all():
            raise ValueError("invalid location")
        if cv2.pointPolygonTest(self.hull,tuple(map(float,a)),False)<0:
            raise ValueError("outside calibrated area")
        return project(self.H,a)
    def speed(self,p0,t0,p1,t1):
        if not all(math.isfinite(x) for x in (t0,t1)) or t1<=t0:
            raise ValueError("nonmonotonic timestamp")
        return float(np.linalg.norm(self.position(p1)-self.position(p0))/(t1-t0))

GEOMETRIES=(
    np.array([[22.,2.,320.],[1.,18.,200.],[.006,.003,1.]]),
    np.array([[16.,-3.,450.],[4.,25.,180.],[.009,-.004,1.]])
)
FIT=((0,0),(20,0),(20,12),(0,12),(10,0),(10,12))
CHECK=((4,3),(10,6),(16,9))

def campaign():
    rows=[]
    for g,H in enumerate(GEOMETRIES):
        cal=Calibration([project(H,p) for p in FIT],FIT,[project(H,p) for p in CHECK],CHECK)
        for fps in FPS:
            for speed in SPEEDS:
                rng=np.random.default_rng(25000+g*100+fps)
                ts=np.arange(fps+1)/fps
                pix=np.array([project(H,(3+speed*t,6)) for t in ts])
                noisy=pix+rng.normal(0,.5,pix.shape)
                def errors(q):
                    e=[abs(cal.speed(q[i-1],ts[i-1],q[i],ts[i])-speed) for i in range(1,len(ts))]
                    return {"mae_mps":float(np.mean(e)),"max_mps":float(max(e))}
                rows.append({"geometry":g,"fps":fps,"truth_mps":speed,"check_rms_m":cal.check_rms_m,
                             "check_max_m":cal.check_max_m,"noiseless":errors(pix),"noise_0_5_pixel":errors(noisy)})
    r={"scope":"i2a_synthetic_planar_calibration_not_field","rows":rows,"cases":len(rows),
       "synthetic_gate_passed":all(x["noiseless"]["max_mps"]<=1e-6 and x["check_max_m"]<=1e-6 for x in rows),
       "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","field_speed_calibration":"NOT_RUN",
       "soak_24h":"NOT_RUN","operational_decision":"abstain","physical_actuation":False,
       "candidate_promoted":False,"operationally_validated":False,"commercial_demo_authorized":False}
    r["result_sha256"]=fingerprint(r)
    return r

def verify(r):
    b=dict(r);sha=b.pop("result_sha256")
    assert fingerprint(b)==sha
    assert r["scope"]=="i2a_synthetic_planar_calibration_not_field" and r["cases"]==24
    assert {(x["geometry"],x["fps"],x["truth_mps"]) for x in r["rows"]}=={(g,f,s) for g in range(2) for f in FPS for s in SPEEDS}
    assert len(r["rows"])==24
    assert r["synthetic_gate_passed"]==all(x["noiseless"]["max_mps"]<=1e-6 and x["check_max_m"]<=1e-6 for x in r["rows"])
    assert r["c3_independent_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION" and r["field_speed_calibration"]==r["soak_24h"]=="NOT_RUN"
    assert r["operational_decision"]=="abstain" and all(r[k] is False for k in ("physical_actuation","candidate_promoted","operationally_validated","commercial_demo_authorized"))
    return r["synthetic_gate_passed"]

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
    r=campaign()
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False)
    assert verify(r), "synthetic mathematical gate failed"
    print(json.dumps({"cases":r["cases"],"synthetic_gate_passed":r["synthetic_gate_passed"]}))

if __name__=="__main__":main()
