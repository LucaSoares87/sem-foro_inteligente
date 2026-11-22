from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from src.archive.contracts import ArchivedRun
from src.archive.service import ArchiveUnavailable

router = APIRouter(prefix="/api/v1/archive", tags=["archive"])

@router.get("/runs")
async def runs(request: Request, after: int = Query(0, ge=0, le=2**63-1),
               limit: int = Query(50,ge=1,le=100),
               intersection: str | None = Query(None, pattern=r"^[A-Z0-9_-]{2,80}$")):
    archive = request.app.state.archive
    try:
        return await archive.execute(archive.store.page, after, limit, intersection)
    except ArchiveUnavailable:
        raise HTTPException(503,"archive_unavailable") from None

@router.get("/runs/{event_id}", response_model=ArchivedRun)
async def run(event_id: UUID, request: Request):
    archive = request.app.state.archive
    if not archive.enabled:
        raise HTTPException(503,"archive_disabled")
    try:
        result = await archive.lookup(event_id)
    except ArchiveUnavailable:
        raise HTTPException(503,"archive_unavailable") from None
    if result is None:
        raise HTTPException(404,"archive_not_found")
    return result

@router.get("/runs/{event_id}/replay")
async def replay(event_id: UUID, request: Request):
    archived = await run(event_id, request)
    baseline = archived.events[0].timestamp
    frames = [{"offset_ms":max(0,(e.timestamp-baseline).total_seconds()*1000),
               "event":e} for e in archived.events]
    return {"mode":"read_only", "origin":"synthetic", "event_id":event_id,
            "decision":"abstain","journal_epoch":archived.journal_epoch,"frames":frames,"report":archived.report}
