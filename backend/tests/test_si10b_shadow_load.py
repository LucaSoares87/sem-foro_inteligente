import asyncio

import pytest

from src.analytics.contracts import SourceGeometry
from src.benchmarking.si10b_shadow_load import LatestReplay, run_load, read_load_inputs, CASES
from src.vision.contracts import ModelSpec


def geometry():
    return SourceGeometry.model_validate({"source_id":"BELLEVUE_116TH_NE12TH",
        "intersection_code":"BELLEVUE_116TH_NE12TH",
        "regions":[{"region_id":"left","xyxy":[0,0,.5,1]},{"region_id":"right","xyxy":[.5,0,1,1]}],
        "lines":[{"line_id":"l1","start":[.4,0],"end":[.4,1]},{"line_id":"l2","start":[.6,0],"end":[.6,1]}],
        "approaches":[{"approach_id":"a","service_group":"A","region_id":"left","discharge_line_id":"l1",
                       "discharge_direction":"negative_to_positive","storage_capacity_vehicles":12},
                      {"approach_id":"b","service_group":"B","region_id":"right","discharge_line_id":"l2",
                       "discharge_direction":"negative_to_positive","storage_capacity_vehicles":12}]})


def test_single_latest_slot_per_source():
    a,b=CASES
    replay=LatestReplay({a:[],b:[]},5)
    replay.publish(a,b"first")
    replay.publish(a,b"second")
    replay.publish(b,b"other")
    assert len(replay.slots)==2
    frame=replay.take_latest(a)
    assert frame.sequence==2 and frame.jpeg==b"second"
    assert frame.session_id==replay.sessions[a].session_id
    assert replay.overwritten[a]==1 and replay.taken[a]==1
    assert replay.take_latest(a) is None and replay.take_latest(b).jpeg==b"other"


class SlowFixtureWorker:
    """Synthetic unit-test fixture only, never used by the real benchmark CLI."""
    def __init__(self,*args):
        self.closed=False
    async def open(self):
        pass
    async def infer(self,jpeg):
        await asyncio.sleep(.25)
        return {"state":"ok","inference_ms":250.,"detections":[]}
    async def close(self):
        self.closed=True


def test_overload_keeps_accounting_and_abstains():
    spec=ModelSpec(filename="fixture.onnx",sha256="a"*64,provenance="fixture",license_ref="fixture")
    result=asyncio.run(run_load({k:[b"fixture"]*4 for k in CASES},5,1,spec,".",geometry(),
        worker_factory=SlowFixtureWorker))
    assert result["max_pending_per_source"]==1
    assert result["optimization_state"]=="abstain" and result["physical_actuation"] is False
    assert result["meets_all_load_gates"] is False
    assert sum(s["overwritten"] for s in result["sources"])>0
    for s in result["sources"]:
        assert s["offered"]==4==s["processed"]+s["overwritten"]
        assert s["completed_within_window"]<=s["processed"]
        assert s["processed"]>0


def test_rejects_wrong_source_and_rate(tmp_path):
    p=tmp_path/"fake.mp4"
    p.write_bytes(b"fake")
    with pytest.raises(ValueError,match="identity"):
        read_load_inputs(CASES[0],p)
    with pytest.raises(ValueError,match="workload"):
        asyncio.run(run_load({CASES[0]:[b"x"]},30,1,None,".",geometry()))
