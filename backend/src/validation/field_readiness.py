"""Private, offline preparation only. No gate registration or controller integration."""
import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import zipfile
from src.archive.store import fingerprint
from src.validation.io import sha256_file
from src.validation.si13_field_packet import prepare as prepare_si13
from src.benchmarking.pimcat_c3_study import COMMON, blank_reference
from src.benchmarking.pimcat_c3_vision import Person
from src.benchmarking.pimcat_i2a_calibration import Calibration
from src.benchmarking.pimcat_i2b_resilience import verify as verify_soak
from src.benchmarking.pimcat_i2c_reference import CLIPS, REVISION, read_reference
from src.vision.model_artifacts import YOLOX_S_SHA256

BLOBS=dict(zip(CLIPS,("9a5b1125e3f7de95e27c799480cc4ca38d940e97","b1af42bddf5bc8fd072a86d41a702fc59e3a6ab2","8ec52082790c71948e56afbdc9124037dfe3ea66")))
MIB=1024*1024
MAX_JSON=64*MIB
BASE="0719edf1b35fe8a2359e88f52d2c8d840d65d50c"

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(x):
    return isinstance(x,str) and re.fullmatch(r"[0-9a-f]{64}",x) is not None

def ref(x):
    return isinstance(x,str) and 0<len(x.strip())<=240

def number(x):
    return type(x) in (int,float) and math.isfinite(x)

def read(path):
    p=Path(path);require(p.is_file() and 0<p.stat().st_size<=MAX_JSON,"invalid JSON size")
    return json.loads(p.read_text(encoding="utf-8"))

def private_path(path):
    p=Path(path).resolve()
    require(not any((a/".git").exists() for a in (p,*p.parents)),"private outputs must be outside checkout")
    return p

def write(path,data):
    p=private_path(path)
    with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,sort_keys=True,allow_nan=False)

def result(scope,**data):
    r={"scope":scope,"base_revision":BASE,**data,"pilot_ready":False,"physical_actuation":False,
       "candidate_promoted":False,"operationally_validated":False,"commercial_demo_authorized":False,
       "human_acceptance":"PENDING_HUMAN","operational_decision":"abstain","gate_registered":False}
    r["result_sha256"]=fingerprint(r);return r

def packet(root,pixel_hash):
    require(digest(pixel_hash),"preflight pixel hash required")
    root=private_path(root);root.mkdir(mode=0o700,parents=False,exist_ok=False)
    # Existing SI13 writes schemas and draft only. umask protects nested files.
    old=os.umask(0o077)
    try:
        prepare_si13(root/"si13")
        for name in ("annotation-a.json","annotation-b.json"):
            write(root/name,blank_reference(pixel_hash))
        write(root/"readiness.json",result("preparation_only",c3="BLOCKED_BY_INDEPENDENT_ANNOTATION",
             jaad="BLOCKED_PENDING_MEDIA_AND_REVIEW",calibration="NOT_RUN",hardware="NOT_RUN",soak_24h="NOT_RUN"))
    finally:os.umask(old)

def c3_compare(a,b,reviewer,pixel_hash):
    require(digest(pixel_hash) and ref(reviewer),"pixel hash and reviewer required")
    for d in (a,b):
        require(d.get("status")=="REVIEWED" and d.get("pixel_sha256")==pixel_hash
                and d.get("model_sha256")==YOLOX_S_SHA256 and ref(d.get("annotator_ref")),"invalid submission")
        rows=d.get("frames",[])
        require(isinstance(rows,list) and [x.get("frame") for x in rows]==list(COMMON)
                and all(type(x["frame"]) is int for x in rows),"incomplete frame coverage")
        for row in rows:
            require(row.get("reviewed") is True and isinstance(row.get("boxes"),list),"explicit review required")
            for box in row["boxes"]:
                require(isinstance(box,list) and len(box)==4 and all(number(x) for x in box),"invalid box")
                Person(tuple(box),1)
            require(len({tuple(x) for x in row["boxes"]})==len(row["boxes"]),"duplicate box")
    require(len({a["annotator_ref"].strip(),b["annotator_ref"].strip(),reviewer.strip()})==3,"separate reviewers required")
    diff=[x["frame"] for x,y in zip(a["frames"],b["frames"]) if x!=y]
    return result("private_c3_submission_comparison",submission_sha256=[fingerprint(a),fingerprint(b)],
        reviewed_frames=len(COMMON),divergent_frames=diff,review_required=True,
        independence_authenticated=False,precision=None,c3="BLOCKED_PENDING_EXTERNAL_REVIEW")

def import_jaad(archive,xml_root,manifest,output):
    require(manifest.get("origin")=="official_jaad_2_0" and manifest.get("revision")==REVISION
        and manifest.get("video_license")=="CC BY 4.0" and all(ref(manifest.get(k)) for k in
        ("provenance_ref","authorization_ref","license_review_ref","attribution_ref")),"reviewed provenance required")
    require(digest(manifest.get("archive_sha256")) and sha256_file(archive)==manifest["archive_sha256"],"archive hash mismatch")
    output=private_path(output)
    require(not output.exists(),"output exists")
    refs={}
    for clip in CLIPS:
        p=Path(xml_root)/(clip+".xml")
        d=read_reference(p,clip,BLOBS[clip])
        refs[clip]={"xml_sha256":d["xml_sha256"],"xml_git_blob":BLOBS[clip],"reference_frames":len(d["frames"]),
                    "excluded_frames":len(d["excluded"]),"annotation_width":d["width"],"annotation_height":d["height"],"annotation_size":d["size"]}
    with zipfile.ZipFile(archive) as z:
        selected={}
        for info in z.infolist():
            name=PurePosixPath(info.filename)
            if name.name not in {c+".mp4" for c in CLIPS}:continue
            clip=name.stem
            require(clip not in selected and not name.is_absolute() and ".." not in name.parts
                    and "\\" not in info.filename and not info.is_dir() and not info.flag_bits&1
                    and (info.external_attr>>16)&0o170000!=0o120000,"unsafe or duplicate member")
            require(0<info.file_size<=128*MIB,"clip size limit")
            selected[clip]=info
        require(set(selected)==set(CLIPS) and sum(i.file_size for i in selected.values())<=256*MIB,"selection or total limit")
        output.mkdir(mode=0o700,exist_ok=False)
        for clip,info in sorted(selected.items()):
            target=output/(clip+".mp4");n=0;h=hashlib.sha256()
            with z.open(info) as src,os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb") as dst:
                for chunk in iter(lambda:src.read(MIB),b""):
                    n+=len(chunk);require(n<=info.file_size and n<=128*MIB,"expanded size limit");dst.write(chunk);h.update(chunk)
            require(n==info.file_size,"member size mismatch")
            refs[clip].update(video_sha256=h.hexdigest(),video_bytes=n)
        report=result("private_jaad_import_not_evaluation",archive_sha256=manifest["archive_sha256"],
            receipt_sha256=fingerprint(manifest),clips=refs,alignment_review="PENDING",origin_authenticated=False)
        write(output/"import-report.json",report)
        return report

def stamp(s):
    d=datetime.fromisoformat(s);require(d.tzinfo is not None,"aware timestamp required");return d

def calibration(data):
    require(all(ref(data.get(k)) for k in ("camera_ref","geometry_ref","operator_ref","reviewer_ref","metric_instrument_ref","speed_instrument_ref","clock_review_ref","threshold_approval_ref")),"missing calibration references")
    require(data["operator_ref"].strip()!=data["reviewer_ref"].strip(),"independent reviewer required")
    require(digest(data.get("capture_sha256")) and stamp(data["approved_at"])<stamp(data["measured_at"]),"capture identity or preapproval missing")
    limits=data["limits"]
    require(set(limits)=={"rms_m","max_m","speed_mae_mps","speed_max_mps"} and all(number(x) and x>0 for x in limits.values()),"invalid approved limits")
    w,h=data["resolution"];require(type(w)is int and type(h)is int and w>0 and h>0,"invalid resolution")
    def in_image(p):
        return len(p)==2 and all(number(x) for x in p) and 0<=p[0]<w and 0<=p[1]<h
    require(all(in_image(p) for p in data["fit_pixels"]+data["check_pixels"]),"pixel outside image")
    cal=Calibration(data["fit_pixels"],data["fit_meters"],data["check_pixels"],data["check_meters"])
    intervals=data["intervals"];require(isinstance(intervals,list) and 3<=len(intervals)<=10000,"independent intervals required")
    errors=[]
    for x in intervals:
        require(x.get("associated") is True and in_image(x["p0"]) and in_image(x["p1"]) and all(number(x[k]) for k in ("t0","t1","reference_mps")) and x["reference_mps"]>=0,"invalid interval")
        errors.append(abs(cal.speed(x["p0"],x["t0"],x["p1"],x["t1"])-x["reference_mps"]))
    metrics={"rms_m":cal.check_rms_m,"max_m":cal.check_max_m,"speed_mae_mps":sum(errors)/len(errors),"speed_max_mps":max(errors)}
    return result("private_calibration_consistency_not_field_approval",input_sha256=fingerprint(data),intervals=len(errors),
        metrics=metrics,meets_supplied_limits=all(metrics[k]<=limits[k] for k in limits),independence_authenticated=False)

def hardware(probe):
    d=dict(probe);h=d.pop("artifact_sha256",None)
    expected=hashlib.sha256(json.dumps(d,separators=(",",":"),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    require(h==expected and d.get("physical_actuation") is False and d.get("pilot_gate_satisfied") is False,"invalid probe")
    p=d["probe"];w=d["workload_observation"]
    positive=lambda v:type(v)is int and v>0
    complete=(d["evidence_state"]=="measured" and p["errors"]==0 and positive(p["samples_requested"])
        and p["samples_ready"]==p["samples_requested"] and w["authorized_candidate_model_loaded"] is True
        and positive(w["physical_sources_running"]) and all(positive(w[k]) for k in
        ("vision_processed_delta","tracking_processed_delta","analytics_processed_delta"))
        and any(positive(v) for v in w["video_frames_delta"].values()))
    require(number(p["elapsed_seconds"]) and p["elapsed_seconds"]>0 and number(p["latency_p95_ms"]) and p["latency_p95_ms"]>=0,"invalid probe timing")
    return result("private_probe_consistency_not_hardware_gate",input_sha256=h,workload_progress_observed=bool(complete),
        http_latency_p95_ms=p["latency_p95_ms"],fps_by_source=None,source_latency_ms=None,inference_latency_ms=None,
        pipeline_cpu_rss=None,additional_measurements_required=True)

def soak(report):
    # Existing verifier uses assertions, so do not accept optimized Python.
    require(__debug__,"assertions must be enabled")
    passed=verify_soak(report)
    full=report["profile"]=="dedicated" and report["elapsed_seconds"]>=86400 and report["soak_24h"]=="EXECUTED_SYNTHETIC"
    return result("synthetic_soak_review_not_field",input_sha256=report["result_sha256"],
        full_duration_reported=full,synthetic_technical_gate_passed=bool(full and passed),field_recovery="NOT_RUN")

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("prepare");a.add_argument("--directory",required=True);a.add_argument("--pixel-sha256",required=True)
    a=sub.add_parser("c3-compare");a.add_argument("--a",required=True);a.add_argument("--b",required=True);a.add_argument("--reviewer-ref",required=True);a.add_argument("--pixel-sha256",required=True);a.add_argument("--output",required=True)
    a=sub.add_parser("jaad-import");a.add_argument("--archive",required=True);a.add_argument("--xml-directory",required=True);a.add_argument("--receipt",required=True);a.add_argument("--directory",required=True)
    for name in ("calibration","hardware","soak"):
        a=sub.add_parser(name);a.add_argument("--input",required=True);a.add_argument("--output",required=True)
    a=p.parse_args()
    if a.command=="prepare":packet(a.directory,a.pixel_sha256)
    elif a.command=="jaad-import":import_jaad(a.archive,a.xml_directory,read(a.receipt),a.directory)
    elif a.command=="c3-compare":write(a.output,c3_compare(read(a.a),read(a.b),a.reviewer_ref,a.pixel_sha256))
    else:write(a.output,{"calibration":calibration,"hardware":hardware,"soak":soak}[a.command](read(a.input)))

if __name__=="__main__":main()
