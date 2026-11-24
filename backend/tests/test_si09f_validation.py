import pytest
from src.analytics.contracts import SourceGeometry
from src.analytics.engine import TrafficEngine
from src.archive.store import fingerprint
from src.benchmarking.si09d_preflight import SOURCE_NAME, SOURCE_SHA, prepare
from src.benchmarking.si09f_validation import Annotation, Review, HOLDOUTS, expected_keys, gate

CASE="morning_0708"

@pytest.fixture
def inputs():
    geo=SourceGeometry.model_validate({"source_id":"CAM_01","intersection_code":"CR_01",
        "regions":[{"region_id":"r","xyxy":[0,0,1,1]}],
        "lines":[{"line_id":"l","start":[.5,0],"end":[.5,1]}],
        "approaches":[{"approach_id":"a","service_group":"A","region_id":"r","discharge_line_id":"l",
                       "discharge_direction":"negative_to_positive","storage_capacity_vehicles":12}]})
    pre={"source_sha256":HOLDOUTS[CASE][1],"derived_sha256":"a"*64,"decoded_pixel_sha256":"b"*64,
         "frames":960,"fps":30,"source_start_frame_zero_based":1}
    gh=TrafficEngine(geo).geometry_hash
    c,q=expected_keys(geo)
    ref={"case_id":CASE,"video_sha256":"a"*64,"decoded_pixel_sha256":"b"*64,"geometry_sha256":gh,
         "annotation_method":"manual_visual_without_model_predictions","annotator_reference":"pending"}
    v={"geometry_sha256":gh,"decision_state":"abstain","x":None,
       "line_counts":[{"line_id":"l","negative_to_positive":0,"positive_to_negative":0}],
       "queue_by_second":{str(s):{"a":0} for s in range(32)}}
    report={"scope":"paired_diagnostic_not_accuracy","video_sha256":"a"*64,"unique_inferences":960,
            "runs":[{"fps":fps,"frames":32*fps,"variants":{"baseline":v,"temporal_candidate":v}} for fps in (30,15,10,5)]}
    report["result_sha256"]=fingerprint(report)
    labels={"counts":[{"line_id":l,"direction":d,"count":0} for l,d in sorted(c)],
            "queues":[{"second":s,"approach_id":a,"count":0} for s,a in sorted(q)],
            "status":"submitted","full_passage_coverage":True}
    return geo,pre,report,ref,labels

def test_blank_reference_never_counts_as_zero(inputs):
    geo,pre,rep,ref,_=inputs
    a=Annotation.model_validate(ref)
    out=gate(CASE,pre,geo,rep,a,a)
    assert out["state"]=="BLOCKED_BY_INDEPENDENT_ANNOTATION"
    assert out["missing_keys_a"]==34 and out["accuracy_metrics"] is None
    assert out["candidate_promoted"] is False

def test_review_gate_explicit_zero_and_hash_binding(inputs):
    geo,pre,rep,ref,labels=inputs
    a=Annotation.model_validate({**ref,**labels,"annotator_reference":"reviewer-A"})
    b=Annotation.model_validate({**ref,**labels,"annotator_reference":"reviewer-B"})
    assert gate(CASE,pre,geo,rep,a,b)["state"]=="PENDING_INDEPENDENT_REVIEW"
    with pytest.raises(ValueError,match="annotators"):
        gate(CASE,pre,geo,rep,a,a)
    rv=Review(reviewer_reference="reviewer-C",annotation_a_sha256=fingerprint(a.model_dump(mode="json")),
              annotation_b_sha256=fingerprint(b.model_dump(mode="json")),accepted=True)
    out=gate(CASE,pre,geo,rep,a,b,rv)
    assert out["state"]=="REVIEWED_RESEARCH_COMPARISON"
    assert len(out["accuracy_metrics"])==8
    assert all(m["count_relative_error"] is None and m["meets_proposed_count_queue_thresholds"] for m in out["accuracy_metrics"])
    assert out["candidate_promoted"] is False
    with pytest.raises(ValueError,match="review identity"):
        gate(CASE,pre,geo,rep,a,b,rv.model_copy(update={"reviewer_reference":"REVIEWER-a"}))
    with pytest.raises(ValueError,match="hash"):
        gate(CASE,pre,geo,rep,a,b,rv.model_copy(update={"annotation_a_sha256":"c"*64}))

def test_disagreement_and_wrong_identity(inputs):
    geo,pre,rep,ref,labels=inputs
    a=Annotation.model_validate({**ref,**labels,"annotator_reference":"A"})
    changed=[dict(x) for x in labels["counts"]]
    changed[0]["count"]=1
    b=Annotation.model_validate({**ref,**labels,"counts":changed,"annotator_reference":"B"})
    assert gate(CASE,pre,geo,rep,a,b)["state"]=="BLOCKED_BY_ANNOTATION_DISAGREEMENT"
    with pytest.raises(ValueError,match="identity"):
        gate(CASE,pre,geo,rep,a,b.model_copy(update={"video_sha256":"c"*64}))
    with pytest.raises(ValueError,match="report hash"):
        gate(CASE,pre,geo,{**rep,"unique_inferences":1},a,b)
    with pytest.raises(ValueError,match="source mismatch"):
        gate(CASE,{**pre,"source_sha256":"c"*64},geo,rep,a,b)

def test_preflight_old_default_rejects_wrong_source(tmp_path):
    source=tmp_path/SOURCE_NAME
    source.write_bytes(b"not the official source")
    with pytest.raises(ValueError,match="source identity"):
        prepare(source,tmp_path/"out.mkv")
    with pytest.raises(ValueError,match="source identity"):
        prepare(source,tmp_path/"out.mkv",source_name=HOLDOUTS[CASE][0],source_sha=HOLDOUTS[CASE][1])
    assert len(SOURCE_SHA)==64 and not (tmp_path/"out.mkv").exists()
