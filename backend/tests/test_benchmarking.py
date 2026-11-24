import asyncio
from datetime import datetime,timedelta,timezone
import numpy as np
import pytest

from src.analytics.contracts import CountingLine,QueueApproachConfig,Region,SourceGeometry
from src.benchmarking.contracts import FpsBenchmarkCriteria
from src.benchmarking.runner import _should_sample,run_fps_sweep
from src.validation.contracts import DatasetManifest,EvaluationRequest,EvaluationThresholds,GroundTruth,Predictions
from src.vision.contracts import ModelSpec

NOW=datetime(2026,11,24,12,0,tzinfo=timezone.utc)

def manifest(**changes):
    values=dict(schema_version=1,dataset_id="bellevue-fixture",origin="external_real_replay",
        source_id="BELLEVUE_TEST",intersection_code="BELLEVUE_TEST",
        video_filename="fixture.mp4",video_sha256="a"*64,
        provenance="test fixture only",license_ref="test",authorization_ref="research-test",
        commercial_demo_authorized=False,recorded_at=NOW,fps=30,width=640,height=360,
        frame_count=60,classes=("car",))
    values.update(changes)
    return DatasetManifest(**values)

def geometry():
    return SourceGeometry(source_id="BELLEVUE_TEST",intersection_code="BELLEVUE_TEST",
        regions=(
            Region(region_id="LEFT",xyxy=(0,0,.45,1)),
            Region(region_id="RIGHT",xyxy=(.55,0,1,1)),
        ),
        lines=(
            CountingLine(line_id="L_LEFT",start=(.45,0),end=(.45,1)),
            CountingLine(line_id="L_RIGHT",start=(.55,0),end=(.55,1)),
        ),
        approaches=(
            QueueApproachConfig(approach_id="A",service_group="GA",region_id="LEFT",
                discharge_line_id="L_LEFT",discharge_direction="negative_to_positive",
                storage_capacity_vehicles=20,min_stop_seconds=.25,
                visibility_score=.9,visibility_calibrated=True),
            QueueApproachConfig(approach_id="B",service_group="GB",region_id="RIGHT",
                discharge_line_id="L_RIGHT",discharge_direction="positive_to_negative",
                storage_capacity_vehicles=20,min_stop_seconds=.25,
                visibility_score=.9,visibility_calibrated=True),
        ))

def criteria():
    return FpsBenchmarkCriteria(approval_reference="SI-09 benchmark test",
        approved_at=NOW-timedelta(hours=1),reference_fps=30,target_fps=(30,15,10,5),
        max_queue_mae_vehicles=1,max_count_relative_error=.05,max_x_mae_vehicles=1,
        min_preference_agreement=.95,min_common_seconds=2,min_decision_seconds=1,min_x_seconds=1)

class Capture:
    def __init__(self,frames):
        self.frames=frames
        self.index=0
        self.current=None
    def isOpened(self): return True
    def grab(self):
        if self.index>=len(self.frames): return False
        self.current=self.frames[self.index]
        self.index+=1
        return True
    def retrieve(self): return True,self.current
    def release(self): pass

class Worker:
    def __init__(self,*_): pass
    async def open(self): pass
    async def close(self): pass
    async def infer(self,_jpeg):
        return {"inference_ms":1.0,"detections":[
            {"label":"car","confidence":.95,"xyxy":[.15,.3,.25,.55]},
            {"label":"car","confidence":.95,"xyxy":[.75,.3,.85,.55]}
        ]}

def test_sampler_is_exact_for_30hz_source():
    for target,expected in ((30,60),(15,30),(10,20),(5,10)):
        last=-1
        count=0
        for frame in range(1,61):
            take,slot=_should_sample(frame,30,target,last)
            if take:
                count+=1
                last=slot
        assert count==expected

def test_fps_sweep_runs_production_engines_and_recommends_lowest_stable_rate(tmp_path):
    frames=[np.zeros((360,640,3),dtype=np.uint8) for _ in range(60)]
    spec=ModelSpec(filename="model.onnx",sha256="b"*64,provenance="test",
                   license_ref="test",purpose="validation_only",confidence=.25)
    report=asyncio.run(run_fps_sweep(manifest(),tmp_path/"fixture.mp4",spec,tmp_path,
        geometry(),criteria(),worker_factory=Worker,capture_factory=lambda _path:Capture(frames),
        verify=lambda *_: {}))
    assert [run.processed_frames for run in report.runs]==[60,30,20,10]
    assert [run.target_fps for run in report.runs]==[30,15,10,5]
    assert all(item.meets_engineering_stability_criteria for item in report.comparisons)
    assert report.engineering_recommended_min_fps==5
    assert report.origin=="external_real_replay"
    assert report.commercial_demo_authorized is False
    assert report.operationally_validated is False
    assert report.physical_actuation is False
    assert all(run.mean_observation_confidence>.65 for run in report.runs)

def test_external_replay_cannot_be_evaluated_as_field_acceptance():
    external=manifest()
    thresholds=EvaluationThresholds(purpose="field_acceptance",approval_reference="wrong",
        approved_at=NOW-timedelta(hours=1),detection_macro_f1=.8,tracking_match_recall=.8,
        max_identity_switch_rate=.1,count_accuracy=.8)
    predictions=Predictions(dataset_id=external.dataset_id,model_sha256="b"*64,
        geometry_sha256="c"*64,detections=(),tracks=(),counts=())
    truth=GroundTruth(dataset_id=external.dataset_id,annotations=(),counts=())
    with pytest.raises(ValueError,match="external replay"):
        EvaluationRequest(manifest=external,ground_truth=truth,predictions=predictions,
                          thresholds=thresholds)
