"""Private JAAD reference preparation; no automatic assertion of independence."""
import hashlib
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from src.benchmarking.pimcat_c3_vision import Person,iou

REVISION="d2feeac998366e47ecc54e5533c8a3fa61141dda"
CLIPS=("video_0005","video_0015","video_0016")
MAX_XML=16*1024*1024

def git_blob_sha(raw):
    return hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()

def read_reference(path,clip,expected_blob):
    if clip not in CLIPS:raise ValueError("not preregistered")
    p=Path(path)
    if not 0<p.stat().st_size<=MAX_XML:raise ValueError("invalid XML size")
    raw=p.read_bytes()
    if git_blob_sha(raw)!=expected_blob or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("reference identity or XML invalid")
    root=ET.fromstring(raw)
    task=root.find("meta/task")
    if task is None or task.findtext("name")!=clip:raise ValueError("clip mismatch")
    size=int(task.findtext("size"));w=int(task.findtext("original_size/width"));h=int(task.findtext("original_size/height"))
    if not (10<=size<=10000 and w>0 and h>0):raise ValueError("invalid dimensions or length")
    frames={f:[] for f in range(0,min(size,240),6)};excluded=set()
    for track in root.findall("track"):
        label=track.get("label")
        if label not in ("ped","pedestrian","people"):raise ValueError("unknown track label")
        for box in track.findall("box"):
            f=int(box.get("frame"))
            if f not in frames:continue
            outside=box.get("outside")
            if outside not in ("0","1"):raise ValueError("invalid outside")
            if outside=="1":continue
            occlusion=box.findtext("attribute[@name='occlusion']")
            if label=="people" or occlusion=="full":
                excluded.add(f);continue
            if occlusion not in ("none","part"):raise ValueError("unrecognized occlusion")
            coords=tuple(float(box.get(k))/d for k,d in zip(("xtl","ytl","xbr","ybr"),(w,h,w,h)))
            frames[f].append(Person(coords,1))
    return {"clip":clip,"frames":frames,"excluded":excluded,"width":w,"height":h,"size":size,
            "xml_sha256":hashlib.sha256(raw).hexdigest()}

def evaluate_reviewed(reference,predictions,reviewed,*,license_reviewed=False,media_verified=False):
    # Caller must supply independently reviewed alignment/coverage, not detector output.
    if license_reviewed is not True or media_verified is not True:raise ValueError("provenance/review required")
    selected=set(reference["frames"])-reference["excluded"]
    if set(reviewed)!=selected or any(reviewed[f] is not True for f in selected) or len(selected)<10 or set(predictions)!=selected:
        raise ValueError("incomplete reference or predictions")
    tp=fp=fn=0
    for f in sorted(selected):
        truth=reference["frames"][f];pred=[p for p in predictions[f] if p.score>=.25]
        pairs=sorted(((iou(p.box,g.box),i,j) for i,p in enumerate(pred) for j,g in enumerate(truth)),reverse=True)
        usedp=set();usedg=set()
        for overlap,i,j in pairs:
            if overlap<.5:break
            if i not in usedp and j not in usedg:usedp.add(i);usedg.add(j)
        tp+=len(usedp);fp+=len(pred)-len(usedp);fn+=len(truth)-len(usedg)
    if tp+fn==0:raise ValueError("no positive truth")
    return {"frames":len(selected),"excluded_frames":len(reference["excluded"]),"tp":tp,"fp":fp,"fn":fn,
            "precision":tp/(tp+fp) if tp+fp else None,"recall":tp/(tp+fn),
            "f1":2*tp/(2*tp+fp+fn),"independence_authenticated":False,
            "c3_independent_precision":"BLOCKED_BY_INDEPENDENT_ANNOTATION","physical_actuation":False,
            "operationally_validated":False,"candidate_promoted":False,"operational_decision":"abstain"}
