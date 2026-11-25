import copy
import hashlib
import json
import zipfile
import pytest
from src.archive.store import fingerprint
from src.validation import field_readiness as f
from src.benchmarking import pimcat_i2a_calibration as a

def test_private_packet_and_c3(tmp_path):
    p=tmp_path/"packet";f.packet(p,"a"*64)
    assert (p.stat().st_mode&0o777)==0o700
    x=f.read(p/"annotation-a.json");y=f.read(p/"annotation-b.json")
    assert x==y and all(r["boxes"] is None for r in x["frames"])
    with pytest.raises(ValueError):f.c3_compare(x,y,"review","a"*64)
    for v,n in ((x,"a"),(y,"b")):
        v.update(status="REVIEWED",annotator_ref=n)
        for r in v["frames"]:r.update(reviewed=True,boxes=[])
    y["frames"][0]["boxes"]=[[.1,.1,.2,.2]]
    r=f.c3_compare(x,y,"review","a"*64)
    assert r["divergent_frames"]==[1] and r["precision"] is None and not r["pilot_ready"]
    with pytest.raises(ValueError):f.c3_compare(x,y,"a","a"*64)
    with pytest.raises(FileExistsError):f.packet(p,"a"*64)

def test_jaad_local_only_and_bounded(tmp_path,monkeypatch):
    archive=tmp_path/"local.zip"
    with zipfile.ZipFile(archive,"w") as z:
        for clip in f.CLIPS:z.writestr("clips/"+clip+".mp4",b"synthetic-test")
        z.writestr("other.mp4",b"not selected")
    def reference(path,clip,blob):
        return dict(xml_sha256="a"*64,frames={1:[]},excluded=set(),width=100,height=100,size=100)
    monkeypatch.setattr(f,"read_reference",reference)
    m=dict(origin="official_jaad_2_0",revision=f.REVISION,video_license="CC BY 4.0",
        provenance_ref="fixture",authorization_ref="fixture",license_review_ref="fixture",
        attribution_ref="fixture",archive_sha256=f.sha256_file(archive))
    with pytest.raises(ValueError):f.import_jaad(archive,tmp_path,{},tmp_path/"bad")
    out=tmp_path/"imported";r=f.import_jaad(archive,tmp_path,m,out)
    assert set(r["clips"])==set(f.CLIPS) and len(list(out.glob("*.mp4")))==3
    assert not r["origin_authenticated"] and not r["pilot_ready"]
    with zipfile.ZipFile(archive,"a") as z:z.writestr("duplicate/video_0005.mp4",b"bad")
    m["archive_sha256"]=f.sha256_file(archive)
    with pytest.raises(ValueError):f.import_jaad(archive,tmp_path,m,tmp_path/"dupes")

def test_calibration_limits_and_no_approval():
    H=a.GEOMETRIES[0]
    pix=lambda x:list(map(float,a.project(H,x)))
    d=dict(camera_ref="fixture",geometry_ref="fixture",operator_ref="a",reviewer_ref="b",
       metric_instrument_ref="fixture",speed_instrument_ref="fixture",clock_review_ref="fixture",threshold_approval_ref="fixture",
       capture_sha256="a"*64,approved_at="2026-01-01T00:00:00+00:00",measured_at="2026-01-02T00:00:00+00:00",
       limits=dict(rms_m=.1,max_m=.2,speed_mae_mps=.1,speed_max_mps=.2),resolution=[1280,720],
       fit_pixels=[pix(x) for x in a.FIT],fit_meters=list(a.FIT),check_pixels=[pix(x) for x in a.CHECK],check_meters=list(a.CHECK),
       intervals=[dict(p0=pix((3,6)),p1=pix((8,6)),t0=i,t1=i+1,reference_mps=5,associated=True) for i in range(3)])
    r=f.calibration(d);assert r["meets_supplied_limits"] and not r["gate_registered"]
    d["intervals"][0]["reference_mps"]=10
    assert not f.calibration(d)["meets_supplied_limits"]
    d["approved_at"]=d["measured_at"]
    with pytest.raises(ValueError):f.calibration(d)

def test_probe_requires_progress_and_keeps_missing_metrics():
    d=dict(physical_actuation=False,pilot_gate_satisfied=False,evidence_state="measured",
        probe=dict(errors=0,samples_requested=2,samples_ready=2,elapsed_seconds=2,latency_p95_ms=1),
        workload_observation=dict(authorized_candidate_model_loaded=True,physical_sources_running=1,
        vision_processed_delta=2,tracking_processed_delta=2,analytics_processed_delta=2,video_frames_delta={"fixture":2}))
    def signed(d):return {**d,"artifact_sha256":hashlib.sha256(json.dumps(d,separators=(",",":"),sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    r=f.hardware(signed(d));assert r["workload_progress_observed"] and r["fps_by_source"] is None
    d["workload_observation"]["analytics_processed_delta"]=0
    assert not f.hardware(signed(d))["workload_progress_observed"]
    with pytest.raises(ValueError):f.hardware({**d,"artifact_sha256":"0"*64})

def test_soak_short_never_counts(monkeypatch):
    monkeypatch.setattr(f,"verify_soak",lambda r:True)
    r=f.soak(dict(profile="ci",elapsed_seconds=180,soak_24h="NOT_RUN",result_sha256="a"*64))
    assert not r["full_duration_reported"] and not r["synthetic_technical_gate_passed"]
