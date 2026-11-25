import numpy as np
import pytest
from src.benchmarking.pimcat_c3_vision import Person,Geometry,Perception,decode_people,PersonDetector
from src.benchmarking.pimcat_c3_study import blank_reference,independent_metrics,COMMON
from src.vision.contracts import CLASSES

def test_decoder_person_only_and_invalid():
    x=np.zeros((1,8400,85),np.float32)
    x[0,810,:5]=[0,0,1,1,.9];x[0,810,5]=.9
    x[0,820,:5]=[0,0,1,1,.9];x[0,820,7]=.9
    assert len(decode_people(x,(1,640,640)))==1 and 0 not in CLASSES
    x[0,0,5]=float("nan")
    with pytest.raises(ValueError):decode_people(x,(1,640,640))

@pytest.mark.parametrize("topology",["intersection","midblock"])
def test_wait_crossing_and_unknown(topology):
    g=Geometry(topology,((.1,.1,.4,.5),),(.4,.1,.8,.5))
    p=Perception(g);a=Person((.2,.2,.3,.4),.8);c=Person((.5,.2,.6,.4),.9)
    for i in range(7):r=p.update(i/5,[a])
    assert r["intention"]=="candidate" and r["oldest_observed_wait_seconds"]==1.2
    r=p.update(1.4,[c]);assert r["crossing"]=="occupied_observed"
    r=p.update(3,[],occluded=True);assert r["crossing"]=="unknown" and r["demand"]=="possible"
    assert r["oldest_observed_wait_seconds"]==3
    with pytest.raises(ValueError):p.acknowledge(independent_service_confirmed=False,waiting_area_confirmed_empty=True)
    p.acknowledge(independent_service_confirmed=True,waiting_area_confirmed_empty=True)
    assert p.update(4,[])["demand"]=="unknown"
    with pytest.raises(ValueError):p.update(3,[])

def test_ambiguity_low_confidence_and_button():
    p=Perception()
    a=Person((.2,.2,.3,.4),.9)
    p.update(0,[a]);r=p.update(.2,[a,a])
    assert r["uncertain"] and p.ambiguous==2
    r=p.update(.4,[Person(a.box,.15)],button=True)
    assert r["uncertain"] and r["demand"]=="possible"
    assert p.update(2,[],available=False)["oldest_observed_wait_seconds"]==1.6
    assert p.expired==1

def test_no_camera_only_clearance_and_hash(tmp_path):
    assert Perception().update(0,[])["crossing"]=="unknown"
    f=tmp_path/"bad.onnx";f.write_bytes(b"bad")
    with pytest.raises(ValueError):PersonDetector(f)
    with pytest.raises(ValueError):Geometry("midblock",((0,0,.6,.6),),(.4,.4,.8,.8))

def test_reference_draft_and_one_to_one():
    h="a"*64;a=blank_reference(h);b=blank_reference(h)
    assert independent_metrics({},a,b,"reviewer",h) is None
    for ref,name in ((a,"a"),(b,"b")):
        ref.update(status="REVIEWED",annotator_ref=name)
        for row in ref["frames"]:row.update(reviewed=True,boxes=[[.1,.1,.3,.3]])
    predictions={i:[Person((.1,.1,.3,.3),.9),Person((.1,.1,.3,.3),.8)] for i in COMMON}
    m=independent_metrics(predictions,a,b,"reviewer",h)
    assert m["tp"]==40 and m["fp"]==40 and m["recall"]==1 and m["precision"]==.5
    assert independent_metrics(predictions,a,b,"a",h) is None
    b["frames"][0]["reviewed"]=False
    assert independent_metrics(predictions,a,b,"reviewer",h) is None
