from fastapi import APIRouter,HTTPException,Request
from src.optimization.contracts import OptimizationResult

router=APIRouter(prefix="/api/v1/optimization",tags=["optimization"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.optimization.status()

@router.get("/sources/{source_id}/latest",response_model=OptimizationResult)
async def latest(source_id: str,request: Request):
    if source_id not in request.app.state.video.sessions:
        raise HTTPException(404,"source_not_registered")
    result=request.app.state.optimization.latest(source_id)
    if result is None:
        raise HTTPException(404,"no_current_optimization")
    return result
