import numpy as np
import pytest
from src.benchmarking import pimcat_i2a_calibration as c

def make():
    H=c.GEOMETRIES[0]
    return c.Calibration([c.project(H,p) for p in c.FIT],c.FIT,[c.project(H,p) for p in c.CHECK],c.CHECK)

def test_synthetic_campaign_and_hash():
    a=c.campaign();b=c.campaign()
    assert a==b and c.verify(a)
    a["physical_actuation"]=True
    with pytest.raises(AssertionError):c.verify(a)

def test_invalid_or_missing_reference():
    with pytest.raises(ValueError):c.Calibration(c.FIT,c.FIT,[],[])
    with pytest.raises(ValueError):c.Calibration(c.FIT,c.FIT,c.FIT[:2],c.FIT[:2])
    line=[(i,0) for i in range(4)]
    with pytest.raises(ValueError):c.Calibration(line,line,c.CHECK,c.CHECK)
    with pytest.raises(ValueError):c.Calibration([(0,0),(1,0),(0,1),(np.nan,1)],c.FIT[:4],c.CHECK,c.CHECK)

def test_monotonic_and_inside():
    h=c.GEOMETRIES[0];cal=make()
    a=c.project(h,(3,6));b=c.project(h,(8,6))
    assert cal.speed(a,0,b,1)==pytest.approx(5)
    for t in (0,-1,np.nan):
        with pytest.raises(ValueError):cal.speed(a,0,b,t)
    with pytest.raises(ValueError):cal.position(c.project(h,(-1,6)))
    with pytest.raises(ValueError):cal.position((np.nan,0))
    with pytest.raises(ValueError):c.project(np.array([[1.,0,0],[0,1,0],[0,0,0]]),(1,2))
