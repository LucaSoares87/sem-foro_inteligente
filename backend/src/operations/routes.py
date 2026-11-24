from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool
from src.operations.security import security_status

router=APIRouter(prefix="/api/v1/operations",tags=["operations"])

@router.get("/status")
async def status(request: Request):
    return {
        "security":security_status(request.app.state.settings),
        "observability":request.app.state.operations_metrics.snapshot(),
        "audit":{"enabled":request.app.state.settings.audit_enabled},
        "backup":{"strategy":"pg_dump_custom_format","automatic":False},
    }

@router.get("/metrics",response_class=PlainTextResponse)
async def metrics(request: Request):
    return PlainTextResponse(request.app.state.operations_metrics.prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8")

@router.get("/audit")
async def audit(request: Request,after: int=Query(0,ge=0,le=2**63-1),
                limit: int=Query(50,ge=1,le=100)):
    return await run_in_threadpool(request.app.state.audit_store.page,after,limit)
