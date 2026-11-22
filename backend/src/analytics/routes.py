from fastapi import APIRouter, HTTPException, Request
from src.analytics.contracts import TrafficSnapshot

router=APIRouter(prefix="/api/v1/analytics",tags=["analytics"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.analytics.status()

@router.get("/sources/{source_id}/latest",response_model=TrafficSnapshot)
async def latest(source_id: str,request: Request):
    service=request.app.state.analytics
    if source_id not in service.geometry:
        raise HTTPException(404,"geometry_not_configured")
    result=service.latest(source_id)
    if result is None:
        raise HTTPException(404,"no_current_analytics")
    return result
