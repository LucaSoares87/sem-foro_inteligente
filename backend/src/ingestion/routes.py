from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response
from src.ingestion.contracts import Observation, Receipt
from src.ingestion.engine import DuplicateConflict, IngestionUnavailable

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])

@router.get("/status")
async def status(request: Request):
    return request.app.state.ingestion.status()

@router.post("/observations", status_code=202, response_model=Receipt)
async def submit(observation: Observation, request: Request, response: Response):
    try:
        receipt, duplicate = request.app.state.ingestion.submit(observation)
    except DuplicateConflict:
        raise HTTPException(409, "event_id_conflict") from None
    except IngestionUnavailable:
        raise HTTPException(503, "ingestion_unavailable", headers={"Retry-After":"1"}) from None
    response.headers["Location"] = f"/api/v1/ingestion/observations/{observation.event_id}"
    if duplicate:
        response.status_code = 200
    return receipt

@router.get("/observations/{event_id}", response_model=Receipt)
async def get_receipt(event_id: UUID, request: Request):
    receipt = request.app.state.ingestion.get(event_id)
    if receipt is None:
        raise HTTPException(404, "receipt_not_found")
    return receipt
