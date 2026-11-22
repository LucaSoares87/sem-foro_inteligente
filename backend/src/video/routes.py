from fastapi import APIRouter, HTTPException, Request
from src.video.manager import SourceBusy

router = APIRouter(prefix="/api/v1/video",tags=["video"])

@router.get("/sources")
async def sources(request: Request):
    result = request.app.state.video.status()
    result['inference_connected'] = request.app.state.vision.state == 'ready'
    return result

@router.post("/sources/{source_id}/start",status_code=202)
async def start(source_id: str,request: Request):
    try:
        return request.app.state.video.start(source_id)
    except KeyError:
        raise HTTPException(404,"source_not_registered") from None
    except SourceBusy:
        raise HTTPException(503,"video_capacity_unavailable") from None

@router.post("/sources/{source_id}/stop")
async def stop(source_id: str,request: Request):
    try:
        return await request.app.state.video.stop(source_id)
    except KeyError:
        raise HTTPException(404,"source_not_registered") from None
