"""Offline temporal speed experiment; no runtime/controller integration."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from src.archive.store import fingerprint
from src.benchmarking import pimcat_i2a_calibration as a

SEEDS=tuple(range(26100,26104))
ACCELS=(0.,1.)
METHODS=("consecutive","window_displacement","window_regression")

def estimates(cal,pixels,times,fps,associated=True):
    if associated is not True or fps not in a.FPS:
        raise ValueError("uncertain association or sampling rate")
    t=np.asarray(times,dtype=float)
    if t.ndim!=1 or len(t)!=len(pixels) or not np.isfinite(t).all() or len(t)<2:
        raise ValueError("invalid observations")
    dt=np.diff(t)
    if np.any(dt<=0) or np.any(dt>1.5/fps):
        raise ValueError("invalid clock or sampling gap")
    n=round(.4*fps)
    if len(t)!=n+1 or not math.isclose(t[-1]-t[0],.4,abs_tol=.05/fps):
        raise ValueError("window must cover 0.4 seconds")
    p=np.array([cal.position(v) for v in pixels])
    centered=t-t.mean()
    slope=(centered[:,None]*(p-p.mean(axis=0))).sum(axis=0)/(centered@centered)
    return dict(zip(METHODS,map(float,(np.linalg.norm(p[-1]-p[-2])/dt[-1],
        np.linalg.norm(p[-1]-p[0])/(t[-1]-t[0]),np.linalg.norm(slope)))))

def metrics(errors):
    return {"count":len(errors),"mae_mps":float(np.mean(np.abs(errors))),
            "max_mps":float(np.max(np.abs(errors))),"bias_mps":float(np.mean(errors))}

def aggregate(rows):
    groups={}
    for fps in a.FPS:
        for accel in ACCELS:
            selected=[r for r in rows if r["fps"]==fps and r["acceleration_mps2"]==accel]
            groups[f"{fps}/{accel:g}"]={m:float(np.mean([r["noisy"][m]["mae_mps"] for r in selected])) for m in METHODS}
    gate=all(groups[f"{fps}/0"]["window_regression"]<groups[f"{fps}/0"]["consecutive"]
        and groups[f"{fps}/1"]["window_regression"]<=groups[f"{fps}/1"]["consecutive"] for fps in a.FPS)
    return groups,gate

def campaign():
    rows=[]
    for g,H in enumerate(a.GEOMETRIES):
        cal=a.Calibration([a.project(H,p) for p in a.FIT],a.FIT,[a.project(H,p) for p in a.CHECK],a.CHECK)
        for fps in a.FPS:
            n=round(.4*fps);t=np.arange(fps+1)/fps
            for v in a.SPEEDS:
                for accel in ACCELS:
                    clean=np.array([a.project(H,(3+v*s+.5*accel*s*s,6)) for s in t])
                    for seed in SEEDS:
                        rng=np.random.default_rng(seed)
                        noisy=clean+rng.normal(0,.5,clean.shape)
                        errs={m:[] for m in METHODS};ideal={m:[] for m in METHODS};formula={m:[] for m in METHODS}
                        for i in range(n,fps+1):
                            sl=slice(i-n,i+1);truth=v+accel*t[i]
                            x=estimates(cal,clean[sl],t[sl],fps);y=estimates(cal,noisy[sl],t[sl],fps)
                            for m in METHODS:
                                width=1/fps if m=="consecutive" else .4
                                errs[m].append(y[m]-truth);ideal[m].append(x[m]-truth)
                                formula[m].append(x[m]-(truth-.5*accel*width))
                        rows.append({"geometry":g,"fps":fps,"initial_mps":v,"acceleration_mps2":accel,"seed":seed,
                           "noisy":{m:metrics(errs[m]) for m in METHODS},
                           "noiseless_instantaneous":{m:metrics(ideal[m]) for m in METHODS},
                           "noiseless_formula":{m:metrics(formula[m]) for m in METHODS}})
    groups,gate=aggregate(rows)
    r={"scope":"i2c_temporal_synthetic_not_field","cases":len(rows),"rows":rows,"groups":groups,
       "research_gate_passed":gate,"technical_gate_passed":all(r["noiseless_formula"][m]["max_mps"]<=1e-6 for r in rows for m in METHODS),
       "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","external_benchmark":"BLOCKED_PENDING_MEDIA_AND_REVIEW",
       "field_speed_calibration":"NOT_RUN","soak_24h":"NOT_RUN","physical_actuation":False,
       "candidate_promoted":False,"operationally_validated":False,"commercial_demo_authorized":False,"operational_decision":"abstain"}
    r["result_sha256"]=fingerprint(r)
    return r

def verify(report):
    r=dict(report);h=r.pop("result_sha256");assert fingerprint(r)==h
    assert r["scope"]=="i2c_temporal_synthetic_not_field" and r["cases"]==len(r["rows"])==192
    assert {(x["geometry"],x["fps"],x["initial_mps"],x["acceleration_mps2"],x["seed"]) for x in r["rows"]}=={(g,f,v,a1,s) for g in range(2) for f in a.FPS for v in a.SPEEDS for a1 in ACCELS for s in SEEDS}
    for x in r["rows"]:
        for k in ("noisy","noiseless_instantaneous","noiseless_formula"):
            assert set(x[k])==set(METHODS)
            for m in METHODS:
                z=x[k][m]
                assert z["count"]==x["fps"]-round(.4*x["fps"])+1
                assert all(math.isfinite(z[p]) for p in ("mae_mps","max_mps","bias_mps"))
                assert 0<=z["mae_mps"]<=z["max_mps"]+1e-12 and abs(z["bias_mps"])<=z["mae_mps"]+1e-12
    groups,gate=aggregate(r["rows"])
    assert r["groups"]==groups and r["research_gate_passed"]==gate
    assert r["technical_gate_passed"]==all(x["noiseless_formula"][m]["max_mps"]<=1e-6 for x in r["rows"] for m in METHODS)
    assert r["c3_independent_precision"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION" and r["external_benchmark"]=="BLOCKED_PENDING_MEDIA_AND_REVIEW"
    assert r["field_speed_calibration"]==r["soak_24h"]=="NOT_RUN"
    assert r["operational_decision"]=="abstain" and all(r[k] is False for k in ("physical_actuation","candidate_promoted","operationally_validated","commercial_demo_authorized"))
    return r["technical_gate_passed"]

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);args=p.parse_args()
    r=campaign()
    with Path(args.output).open("x",encoding="utf-8") as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False)
    print(json.dumps({"groups":r["groups"],"research_gate_passed":r["research_gate_passed"]},sort_keys=True))
    assert verify(r),"technical mathematical gate failed"

if __name__=="__main__":main()
