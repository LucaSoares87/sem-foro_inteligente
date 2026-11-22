from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from src.pipeline.contracts import PipelineReport
from src.archive.service import ArchiveUnavailable

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.pipeline.status()

@router.get("/reports/{event_id}", response_model=PipelineReport)
async def report(event_id: UUID, request: Request):
    value = request.app.state.pipeline.get(event_id)
    if value is None or request.app.state.archive.enabled:
        try:
            archived = await request.app.state.archive.lookup(event_id)
        except ArchiveUnavailable:
            raise HTTPException(503, "archive_unavailable") from None
        if archived is None:
            raise HTTPException(404, "report_not_found")
        value = archived.report
    return value

@router.get("/events")
async def events(request: Request, after: int = Query(0, ge=0, le=2**63-1), limit: int = Query(100, ge=1, le=200), epoch: UUID | None = None):
    return request.app.state.pipeline.events.read(after, limit, epoch)
