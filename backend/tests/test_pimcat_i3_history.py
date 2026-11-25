import copy
from datetime import date,timedelta
import pytest
from src.reporting.daily import daily_report,bounds
from src.archive.store import fingerprint
from src.benchmarking import pimcat_i3_history as i
from test_predictive import make_windows

DAY=date(2026,1,1)

def fixture(day,count=10,full=True,limited=False,epoch=None):
    a=make_windows(1)[0];start,end=bounds(day)
    if not full:end=start+timedelta(seconds=60)
    updates={"started_at":start,"ended_at":end,"duration_seconds":(end-start).total_seconds(),"skipped_frames":int(limited),
             "lines":tuple(l.model_copy(update={"negative_to_positive":count,"positive_to_negative":count}) for l in a.lines)}
    if epoch is not None:updates["analytics_epoch"]=epoch
    return daily_report("CR_01",day,{"CAM_01":[a.model_copy(update=updates)]})

def rehash(r):
    r.pop("report_sha256",None);r["report_sha256"]=fingerprint(r);return r

def test_full_comparison_and_exclusive_write(tmp_path):
    from uuid import UUID
    epoch=UUID(int=42)
    a=fixture(DAY,0,epoch=epoch);b=fixture(DAY+timedelta(days=1),24,epoch=epoch)
    r=i.build([b,a]);assert r==i.build([a,b])
    assert r["comparisons"] and all(x["difference_per_hour"]==1 and x["percent_change"] is None for x in r["comparisons"])
    assert r["physical_speed"] is None and r["camera_availability"] is None and not r["physical_actuation"]
    path=tmp_path/"result.json";i.write_private(path,r)
    with pytest.raises(FileExistsError):i.write_private(path,r)

def test_null_coverage_limited_lineage_and_gaps():
    from uuid import UUID
    epoch=UUID(int=42);a=fixture(DAY,epoch=epoch)
    for opts,reason in (({"full":False},"partial_coverage"),({"limited":True},"limited_quality"),({"epoch":UUID(int=43)},"series_missing_or_lineage_changed")):
        kw={"epoch":epoch,**opts};b=fixture(DAY+timedelta(days=1),**kw)
        result=i.build([a,b]);assert all(x["reason"]==reason and x["difference_per_hour"] is None for x in result["comparisons"])
    b=fixture(DAY+timedelta(days=2),epoch=epoch)
    assert i.build([a,b])["missing_dates"]==["2026-01-02"] and not i.build([a,b])["comparisons"]
    e=daily_report("CR_01",DAY+timedelta(days=1),{"CAM_01":[]})
    assert all(x["reason"]=="series_missing_or_lineage_changed" for x in i.build([a,e])["comparisons"])

def test_integrity_and_limits():
    a=fixture(DAY);b=copy.deepcopy(a);b["date"]="2026-01-02"
    with pytest.raises(ValueError):i.build([b])
    with pytest.raises(ValueError):i.build([a,a])
    with pytest.raises(ValueError):i.build([a,fixture(DAY+timedelta(days=31))])
    b=copy.deepcopy(a);b["physical_actuation"]=True
    with pytest.raises(ValueError):i.build([rehash(b)])
    b=copy.deepcopy(a);b["series"][0]["coverage_fraction"]=.3
    with pytest.raises(ValueError):i.build([rehash(b)])
