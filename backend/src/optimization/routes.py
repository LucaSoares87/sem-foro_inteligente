from fastapi import APIRouter,HTTPException,Query,Request
from starlette.concurrency import run_in_threadpool
from src.optimization.contracts import OptimizationResult
from src.archive.store import fingerprint

router=APIRouter(prefix="/api/v1/optimization",tags=["optimization"])

def current_result(state,source_id):
    """Expose a preference only when it belongs to the current queue epoch and frame."""
    snapshot=state.queue_intelligence.latest(source_id)
    result=state.optimization.latest(source_id)
    if snapshot is None or result is None:
        return None
    # Match the immutable state identity emitted by dynamic_clear_first_v1.
    payload={"algorithm":result.algorithm,"source_id":snapshot.source_id,
        "intersection_code":snapshot.intersection_code,"frame_sequence":snapshot.frame_sequence,
        "queue_epoch":str(snapshot.queue_epoch),"geometry_sha256":snapshot.geometry_sha256,
        "model_sha256":snapshot.model_sha256,"data_origin":snapshot.data_origin,
        "approaches":[a.model_dump(mode="json") for a in snapshot.approaches]}
    return result if fingerprint(payload)==result.state_sha256 else None

@router.get("/status")
async def status(request: Request):
    state=request.app.state
    report=state.optimization.status()
    results=[r.model_dump(mode="json") for source_id in sorted(state.video.sessions)
             if (r:=current_result(state,source_id)) is not None]
    return {**report,"sources":results,"state":"available" if results else "idle"}

@router.get("/sources/{source_id}/latest",response_model=OptimizationResult)
async def latest(source_id: str,request: Request):
    if source_id not in request.app.state.video.sessions:
        raise HTTPException(404,"source_not_registered")
    result=current_result(request.app.state,source_id)
    if result is None:
        raise HTTPException(404,"no_current_optimization")
    return result


@router.get("/sources/{source_id}/history")
async def history(source_id: str,request: Request,limit: int=Query(60,ge=1,le=120)):
    if source_id not in request.app.state.video.sessions:
        raise HTTPException(404,"source_not_registered")
    rows=await run_in_threadpool(request.app.state.queue_store.recent_experiments,source_id,limit)
    return {"source_id":source_id,"items":[row.model_dump(mode="json") for row in rows]}
