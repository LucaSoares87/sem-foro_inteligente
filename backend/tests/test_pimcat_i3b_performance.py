import copy
import pytest
from src.archive.store import fingerprint
from src.benchmarking import pimcat_i3b_performance as p

def rehash(r):
    r.pop("minute_sha256",None);r["minute_sha256"]=fingerprint(r)

def test_fixture_denominators_and_quantiles():
    records,a,b,s=p.fixture();r=p.build(records,a,b,s)
    assert r["expected_interval_source_minutes"]==6 and r["received_source_minutes"]==5
    assert r["missing_minutes"]==[{"source_id":"LAB_B","minute":"2026-01-01T00:01:00+00:00"}]
    x,y=r["aggregates"]
    assert x["recent_slots"]==180 and x["recent_share_observed"]==1
    assert y["expected_slots"]==120 and y["observed_slots"]==90 and y["recent_slots"]==30
    assert y["unknown_slots"]==60 and y["unobserved_slots"]==30
    assert y["recent_share_observed"]==pytest.approx(1/3)
    assert y["recent_fraction_lower"]==.25 and y["recent_fraction_upper"]==.5
    assert y["fps"]["count"]==30 and y["decode_receive_ms"]=={"count":30,"p50":1.4,"p95":2.8,"max":2.9}
    assert r["camera_uptime_physical"] is None and r["source_latency_ms"] is None
    assert r["operational_decision"]=="abstain" and not r["physical_actuation"]
    assert r==p.build(list(reversed(records)),a,b,list(reversed(s)))

def test_empty_and_configuration_separation():
    records,a,b,s=p.fixture();records[0]["samples"]=[];rehash(records[0])
    records[1]["config_sha256"]="b"*64;rehash(records[1])
    r=p.build(records,a,b,s);x=r["minutes"][0]
    assert x["coverage"]==0 and x["recent_share_observed"] is None
    assert x["recent_fraction_lower"]==0 and x["recent_fraction_upper"]==1
    assert x["fps"]["p95"] is None and len(r["aggregates"])==3
    assert len(p.build([],a,b,s)["missing_minutes"])==6

def test_integrity_scope_and_duplicate_rejection():
    records,a,b,s=p.fixture()
    for mutate in (lambda x:x["samples"][0].update(slot=60),
                   lambda x:x["samples"][0].update(recent=False),
                   lambda x:x["samples"].append(x["samples"][0]),
                   lambda x:x.update(origin="field"),
                   lambda x:x.update(config_sha256="bad")):
        x=copy.deepcopy(records[0]);mutate(x);rehash(x)
        with pytest.raises(ValueError):p.build([x],a,b,s)
    x=copy.deepcopy(records[0]);x["samples"][0]["fps"]=7
    with pytest.raises(ValueError):p.build([x],a,b,s)
    x=copy.deepcopy(records[0]);x["config_sha256"]="b"*64;rehash(x)
    with pytest.raises(ValueError):p.build([records[0],x],a,b,s)
    with pytest.raises(ValueError):p.build(records,a,b,["LAB_A"])
    with pytest.raises(ValueError):p.build(records,a,"2026-01-03T00:00:00+00:00",s)
    with pytest.raises(ValueError):p.build(records,a,b,["LAB_A"]*33)

def test_digest_exclusive_export(tmp_path):
    r=p.build(*p.fixture());d=dict(r);h=d.pop("result_sha256")
    assert fingerprint(d)==h
    path=tmp_path/"report.json";p.write_exclusive(path,r)
    with pytest.raises(FileExistsError):p.write_exclusive(path,r)
