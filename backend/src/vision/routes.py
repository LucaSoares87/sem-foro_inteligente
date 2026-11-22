from fastapi import APIRouter, HTTPException, Request
from src.vision.contracts import DetectionBatch

router=APIRouter(prefix="/api/v1/vision",tags=["vision"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.vision.status()

@router.get("/sources/{source_id}/latest",response_model=DetectionBatch)
async def latest(source_id: str, request: Request):
    service=request.app.state.vision
    if source_id not in service.video.sessions:
        raise HTTPException(404,"source_not_registered")
    result=service.valid_result(source_id)
    if result is None:
        raise HTTPException(404,"no_current_detection")
    return result
