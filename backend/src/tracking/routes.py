from fastapi import APIRouter, HTTPException, Request
from src.tracking.contracts import TrackBatch

router=APIRouter(prefix="/api/v1/tracking",tags=["tracking"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.tracking.status()

@router.get("/sources/{source_id}/latest",response_model=TrackBatch)
async def latest(source_id: str,request: Request):
    service=request.app.state.tracking
    if source_id not in service.vision.video.sessions:
        raise HTTPException(404,"source_not_registered")
    result=service.latest(source_id)
    if result is None:
        raise HTTPException(404,"no_current_tracks")
    return result
