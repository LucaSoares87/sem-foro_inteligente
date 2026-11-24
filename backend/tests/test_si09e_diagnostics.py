from datetime import datetime,timezone

import pytest
from src.analytics.contracts import SourceGeometry
from src.analytics.engine import TrafficEngine
from src.benchmarking.si09e_diagnostics import temporal_geometry,replay
from src.benchmarking.si09e_reference import IndependentReference,compare_reference
from src.validation.contracts import DatasetManifest
from src.vision.contracts import ModelSpec

def geometry():
    return SourceGeometry.model_validate({"source_id":"CAM_01","intersection_code":"CR_01",
        "regions":[{"region_id":"r1","xyxy":[0,0,.5,1]},{"region_id":"r2","xyxy":[.5,0,1,1]}],
        "lines":[{"line_id":"l1","start":[.4,0],"end":[.4,1]},{"line_id":"l2","start":[.6,0],"end":[.6,1]}],
        "approaches":[{"approach_id":"a","service_group":"A","region_id":"r1","discharge_line_id":"l1","discharge_direction":"negative_to_positive","storage_capacity_vehicles":12},
                      {"approach_id":"b","service_group":"B","region_id":"r2","discharge_line_id":"l2","discharge_direction":"negative_to_positive","storage_capacity_vehicles":12}]})

def test_temporal_candidate_changes_only_frame_gap():
    geo=geometry()
    for fps,frames in [(30,23),(15,12),(10,8),(5,4)]:
        candidate=temporal_geometry(geo,fps)
        assert candidate.max_gap_frames==frames
        assert candidate.model_dump(exclude={"max_gap_frames"})==geo.model_dump(exclude={"max_gap_frames"})
    assert geo.max_gap_frames==5
    with pytest.raises(ValueError):
        temporal_geometry(geo,7)

def test_empty_reference_never_treated_as_zero():
    geo=geometry()
    data={"video_sha256":"a"*64,"geometry_sha256":TrafficEngine(geo).geometry_hash,
        "status":"draft","annotation_method":"manual_visual_without_model_predictions","annotator_reference":"pending"}
    ref=IndependentReference.model_validate(data)
    report={"scope":"paired_diagnostic_not_accuracy","video_sha256":"a"*64,"result_sha256":"b"*64}
    out=compare_reference(ref,report,geo)
    assert out["metrics"] is None and out["missing_count_keys"]==4 and out["missing_queue_keys"]==64
    with pytest.raises(ValueError,match="identity"):
        compare_reference(ref,{**report,"video_sha256":"c"*64},geo)
    with pytest.raises(ValueError,match="reviewer"):
        IndependentReference.model_validate({**data,"status":"reviewed","full_passage_coverage":True,
            "independent_reviewer_reference":"pending"})

def test_paired_replay_retains_abstention_and_same_samples():
    geo=geometry()
    manifest=DatasetManifest(dataset_id="test",origin="external_real_replay",source_id="CAM_01",
        intersection_code="CR_01",video_filename="clip.mp4",video_sha256="a"*64,
        provenance="test",license_ref="test",authorization_ref="test",
        recorded_at=datetime(2017,1,1,tzinfo=timezone.utc),fps=30,width=1280,height=720,
        frame_count=30,classes=("car",))
    spec=ModelSpec(filename="fixture.onnx",sha256="b"*64,provenance="test",license_ref="test")
    for fps in (30,15,10,5):
        result=replay(manifest,spec,geo,[((),1.)]*30,fps)
        assert result["frames"]==fps
        assert result["unique_confirmed_track_ids"]==0
        assert all(v["decision_state"]=="abstain" and v["x"] is None for v in result["variants"].values())
