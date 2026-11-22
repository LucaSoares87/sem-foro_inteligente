from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response
from src.ingestion.contracts import Observation, Receipt
from src.ingestion.engine import DuplicateConflict, IngestionUnavailable
from src.archive.service import ArchiveUnavailable

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.ingestion.status()

@router.post("/observations", status_code=202, response_model=Receipt)
async def submit(observation: Observation, request: Request, response: Response):
    try:
        engine = request.app.state.ingestion
        existing = engine.get(observation.event_id)
        archived = await request.app.state.archive.lookup(observation.event_id)
        if archived is not None:
            if archived.receipt.observation != observation:
                raise DuplicateConflict
            receipt, duplicate = archived.receipt, True
        elif existing is not None:
            if existing.observation != observation:
                raise DuplicateConflict
            receipt, duplicate = engine.submit(observation)
        else:
            receipt, duplicate = engine.submit(observation)
    except DuplicateConflict:
        raise HTTPException(409, "event_id_conflict") from None
    except (IngestionUnavailable, ArchiveUnavailable):
        raise HTTPException(503, "ingestion_unavailable", headers={"Retry-After":"1"}) from None
    response.headers["Location"] = f"/api/v1/ingestion/observations/{observation.event_id}"
    if duplicate:
        response.status_code = 200
    return receipt

@router.get("/observations/{event_id}", response_model=Receipt)
async def get_receipt(event_id: UUID, request: Request):
    receipt = request.app.state.ingestion.get(event_id)
    archive = request.app.state.archive
    if receipt is None or (archive.enabled and receipt.state == "processed"):
        try:
            archived = await archive.lookup(event_id)
        except ArchiveUnavailable:
            raise HTTPException(503, "archive_unavailable") from None
        if archived is None:
            if receipt is not None:
                raise HTTPException(503, "archive_record_missing")
            raise HTTPException(404, "receipt_not_found")
        receipt = archived.receipt
    return receipt
