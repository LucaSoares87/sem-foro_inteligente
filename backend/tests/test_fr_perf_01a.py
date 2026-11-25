import pytest
from src.benchmarking.fr_perf_01a import Replay, synthetic_frames, KEY
from src.benchmarking.fr_perf_01_accounting import OFFERED
from hashlib import sha256
from time import monotonic

def test_synthetic_schedule_and_identity():
    frames=synthetic_frames()
    assert len(frames)==OFFERED
    assert [sha256(x).hexdigest() for x in frames]==[sha256(x).hexdigest() for x in synthetic_frames()]
    assert len(set(frames))>1

def test_latest_frame_identity():
    r=Replay();r.start=monotonic()
    r.publish(0,b"a");r.publish(1,b"b")
    assert r.overwritten==[0]
    assert r.take_latest(KEY).sequence==2
    assert r.taken.keys()=={1}
    assert r.take_latest(KEY) is None
    with pytest.raises(ValueError):r.publish(1,b"c")
