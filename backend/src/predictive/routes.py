from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from src.predictive.forecast import estimate
from src.predictive.store import HistoryIntegrityError
from src.predictive.history import build_intersection_history

router=APIRouter(prefix="/api/v1/predictive",tags=["predictive"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.history.status()

@router.get("/sources/{source}/history")
async def history(source: str,request: Request,after: int=Query(0,ge=0,le=2**31-1),limit: int=Query(30,ge=1,le=100)):
    service=request.app.state.history
    if not service.enabled:
        raise HTTPException(503,"history_disabled")
    try:
        return await run_in_threadpool(service.store.page,source,after,limit)
    except (SQLAlchemyError,HistoryIntegrityError):
        raise HTTPException(503,"history_unavailable") from None


@router.get("/intersections/{intersection}/history")
async def intersection_history(intersection: str=Path(pattern=r"^[A-Z0-9_-]{2,80}$"),
                               request: Request=None,
                               limit: int=Query(60,ge=2,le=120)):
    service=request.app.state.history
    if not service.enabled:
        raise HTTPException(503,"history_disabled")
    source_ids=sorted(source_id for source_id,session in request.app.state.video.sessions.items()
                      if session.spec.intersection_code==intersection)
    try:
        registered=await run_in_threadpool(request.app.state.geography.store.get,intersection)
        if not source_ids and registered is None:
            raise HTTPException(404,"intersection_not_found")
        histories={}
        for source_id in source_ids:
            histories[source_id]=await run_in_threadpool(service.store.recent_source,source_id,limit)
        return build_intersection_history(intersection,histories)
    except HTTPException:
        raise
    except (SQLAlchemyError,HistoryIntegrityError,ValueError):
        raise HTTPException(503,"history_unavailable") from None

@router.get("/sources/{source}/forecast")
async def forecast(source: str,request: Request,line_id: str=Query(pattern=r"^[A-Za-z0-9_-]{1,40}$"),
                   direction: Literal["negative_to_positive","positive_to_negative"]="negative_to_positive"):
    service=request.app.state.history
    if not service.enabled:
        raise HTTPException(503,"history_disabled")
    current=request.app.state.analytics.latest(source)
    session=request.app.state.video.sessions.get(source)
    if current is None or session is None or session.state!="running":
        return {"state":"insufficient_data","reason":"no_current_live_snapshot","operationally_validated":False}
    if not any(l.line_id==line_id for l in current.lines):
        raise HTTPException(404,"line_not_configured")
    try:
        windows=await run_in_threadpool(service.store.recent,source,current.analytics_epoch)
    except (SQLAlchemyError,HistoryIntegrityError):
        raise HTTPException(503,"history_unavailable") from None
    if not windows or not 0<=(current.received_at-windows[-1].ended_at).total_seconds()<=65:
        return {"state":"insufficient_data","reason":"history_not_recent","operationally_validated":False}
    latest=request.app.state.analytics.latest(source)
    if latest is None or latest.analytics_epoch!=current.analytics_epoch or session.state!="running" or (latest.received_at-windows[-1].ended_at).total_seconds()>65:
        return {"state":"insufficient_data","reason":"session_changed","operationally_validated":False}
    if latest.discontinuities!=windows[-1].discontinuities_at_end:
        return {"state":"insufficient_data","reason":"recent_discontinuity","operationally_validated":False}
    return {**estimate(windows,line_id,direction),"source_id":source,"line_id":line_id,
            "direction":direction,"purpose":current.purpose,"analytics_epoch":current.analytics_epoch,
            "data_through":windows[-1].ended_at}
