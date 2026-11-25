from datetime import date,datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Path, Query, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from src.predictive.store import HistoryIntegrityError
from src.reporting.daily import load_day,ZONE

router=APIRouter(prefix="/api/v1/reporting",tags=["reporting"])

@router.get("/intersections/{intersection}/daily")
async def daily(request:Request,intersection:str=Path(pattern=r"^[A-Z0-9_-]{2,80}$"),day:date=Query(...)):
    if day>datetime.now(ZoneInfo(ZONE)).date() or day.year<2000:
        raise HTTPException(422,"invalid_report_date")
    if not request.app.state.history.enabled:
        raise HTTPException(503,"history_disabled")
    sources=sorted(s for s,session in request.app.state.video.sessions.items()
                   if session.spec.intersection_code==intersection)
    try:
        registered=await run_in_threadpool(request.app.state.geography.store.get,intersection)
        if not sources and registered is None:raise HTTPException(404,"intersection_not_found")
        return await run_in_threadpool(load_day,request.app.state.engine,intersection,day,sources)
    except HTTPException:raise
    except (SQLAlchemyError,HistoryIntegrityError,ValueError,OverflowError):
        raise HTTPException(503,"daily_report_unavailable_or_scan_limit") from None
