import copy
import pytest
from src.archive.store import fingerprint
from src.benchmarking import pimcat_i3c_feedback as f
from src.benchmarking import pimcat_i3b_performance as p

def digest(d,key):
    x=dict(d);h=x.pop(key);assert fingerprint(x)==h

def test_catalog_keeps_all_outcomes_and_lineage():
    r=f.build("2026-12-31")
    assert [x["hypothesis_id"] for x in r["catalog"]]==["I1A","I1B","I1C","I1D"]
    assert [x["status"] for x in r["catalog"]]==["marginal_pass","failed","failed","null_failed"]
    assert r["quality_input_report_sha256"] is None
    assert not any(x["kind"]=="data_quality" for x in r["suggestions"])
    for e in r["catalog"]:digest(e,"entry_sha256")
    for s in r["suggestions"]:
        digest(s,"suggestion_sha256")
        assert not s["parameter_application"] and s["human_review_required"]
    assert r["human_acceptance"]=="PENDING_HUMAN"
    assert not any(r[k] for k in ("physical_actuation","candidate_promoted","automatic_parameter_application","commercial_demo_authorized","operationally_validated"))
    assert r["operational_decision"]=="abstain"
    digest(r,"result_sha256")

def test_quality_rebuilt_and_missing_states_distinct():
    q=f.fixture();r=f.build("2026-11-25",q)
    assert r["quality_input_report_sha256"]==p.build(q["records"],q["start"],q["end"],q["sources"])["result_sha256"]
    data=[s for s in r["suggestions"] if s["kind"]=="data_quality"]
    assert {s["reason"] for s in data}=={"missing_minute","unobserved_slots","unknown_observed_slots"}
    assert len(data)==3
    missing=next(s for s in data if s["reason"]=="missing_minute")
    assert "config_sha256" not in missing["context"]
    assert next(s for s in data if s["reason"]=="unknown_observed_slots")["context"]["count"]==60
    assert next(s for s in data if s["reason"]=="unobserved_slots")["context"]["count"]==30
    q["records"].reverse();q["sources"].reverse()
    assert r==f.build("2026-11-25",q)

def test_missing_metric_and_invalid_inputs():
    q=f.fixture();q["records"][0]["samples"][0]["fps"]=None
    x=q["records"][0];x.pop("minute_sha256");x["minute_sha256"]=fingerprint(x)
    r=f.build("2026-11-25",q)
    assert any(s["reason"]=="metric_missing_in_recent_slot" and s["context"]["metric"]=="fps" and s["context"]["count"]==1 for s in r["suggestions"])
    q=copy.deepcopy(q);x=q["records"][0];x["origin"]="field";x.pop("minute_sha256");x["minute_sha256"]=fingerprint(x)
    with pytest.raises(ValueError):f.build("2026-11-25",q)
    q=f.fixture();q["records"][0]["samples"][0]["fps"]=7
    with pytest.raises(ValueError):f.build("2026-11-25",q)

def test_schedule_and_exclusive_write(tmp_path):
    r=f.build("2026-12-31",f.fixture());s=r["schedule"]
    assert not s["scheduler_installed"] and s["timezone"]=="America/Recife"
    assert [x["target_civil_date"] for x in s["entries"]]==["2026-12-31","2027-01-01","2027-01-02"]
    assert s["entries"][0]["planned_local"]=="2027-01-01T01:00:00-03:00"
    assert s["entries"][0]["planned_utc"]=="2027-01-01T04:00:00+00:00"
    assert all(x["state"]=="PLANNED_NOT_INSTALLED" and not x["execution_authorized"] for x in s["entries"])
    with pytest.raises(ValueError):f.build("2026-2-1")
    path=tmp_path/"feedback.json";f.write_exclusive(path,r)
    with pytest.raises(FileExistsError):f.write_exclusive(path,r)
