from fastapi import APIRouter,HTTPException,Request
from src.queueing.contracts import QueueSnapshot

router=APIRouter(prefix="/api/v1/queue",tags=["queue"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.queue_intelligence.status()

@router.get("/sources/{source_id}/latest",response_model=QueueSnapshot)
async def latest(source_id: str,request: Request):
    if source_id not in request.app.state.video.sessions:
        raise HTTPException(404,"source_not_registered")
    result=request.app.state.queue_intelligence.latest(source_id)
    if result is None:
        raise HTTPException(404,"no_current_queue_state")
    return result
