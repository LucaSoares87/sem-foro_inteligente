import pytest
from src.benchmarking.si09d_preflight import select_span, prepare, STEP

def test_first_continuous_span_excludes_duplicate_and_gap():
    stamps=[0., .00001, .00001+STEP, .00001+2*STEP, 1., 1.+STEP, 1.+2*STEP, 1.+3*STEP]
    assert select_span(stamps,4)==(4,8)
    assert select_span(stamps,3)==(1,4)

def test_drift_is_not_silently_rounded():
    stamps=[i*(STEP+.0005) for i in range(10)]
    with pytest.raises(ValueError,match="no continuous"):
        select_span(stamps,8)

@pytest.mark.parametrize("stamps", [[0,float("nan")],[0,-1],[0,float("inf")]])
def test_nonfinite_or_negative_time_fails(stamps):
    with pytest.raises(ValueError,match="invalid source timestamp"):
        select_span(stamps,2)

def test_wrong_source_never_writes_output(tmp_path):
    source=tmp_path/"wrong.mp4"
    source.write_bytes(b"wrong")
    target=tmp_path/"derived.mkv"
    with pytest.raises(ValueError,match="identity"):
        prepare(source,target)
    assert not target.exists()
