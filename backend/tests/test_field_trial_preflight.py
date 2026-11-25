import pytest
from src.validation import field_trial_preflight as f
from src.archive.store import fingerprint

def approval():
    return dict(scope="private_lab_only",controller_connected=False,physical_actuation=False,
                requested_profile="dedicated",requested_duration_seconds=86400,
                **{k:"fixture-"+k for k in f.APPROVALS})

def host():
    return dict(os="Linux",architecture="x86_64",python="3.12",logical_cpus=8,
                memory_total_bytes=16*1024**3,disk_free_bytes=100*1024**3,ffmpeg_on_path=True,docker_on_path=True)

def test_full_inventory_does_not_authorize():
    r=f.plan(approval(),host());assert not r["missing_approval_refs"] and not r["missing_inventory"]
    assert r["soak_24h"]=="NOT_RUN" and not r["execution_authorized"] and not r["pilot_ready"]
    assert r["hardware_suitable"] is None and not r["approvals_authenticated"]
    h=r.pop("result_sha256");assert fingerprint(r)==h

def test_missing_and_invalid_inputs():
    a=approval();a.pop("cost_authorization_ref")
    h=host();h["memory_total_bytes"]=None;h["ffmpeg_on_path"]=False
    r=f.plan(a,h);assert r["missing_approval_refs"]==["cost_authorization_ref"]
    assert r["missing_inventory"]==["memory_total_bytes","ffmpeg_on_path"]
    a["physical_actuation"]=True
    with pytest.raises(ValueError):f.plan(a,h)
    a=approval();a["requested_duration_seconds"]=180
    with pytest.raises(ValueError):f.plan(a,h)
    a=approval();a["cost_authorization_ref"]=a["host_authorization_ref"]
    with pytest.raises(ValueError):f.plan(a,h)

def test_private_directory(tmp_path):
    d=tmp_path/"private";d.mkdir(mode=0o700)
    assert f.inventory(d)["disk_free_bytes"]>=0
    d.chmod(0o755)
    with pytest.raises(ValueError):f.inventory(d)
