import re
from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from src.operations.logging import get_logger
from src.operations.security import authorize

REQUEST_ID_RE=re.compile(r"^[A-Za-z0-9_.:-]{8,64}$")
logger=get_logger()

def _request_id(headers):
    supplied=(headers.get("x-request-id") or "").strip()
    return supplied if REQUEST_ID_RE.fullmatch(supplied) else uuid4().hex

def _route(request):
    route=request.scope.get("route")
    path=getattr(route,"path",None)
    return path or request.url.path

async def _audit(app,request_id,decision,method,route,status_code,outcome):
    if not app.state.settings.audit_enabled:
        return
    principal=decision.principal
    actor=principal.actor if principal else "unauthenticated"
    roles=principal.roles if principal else frozenset()
    try:
        await run_in_threadpool(app.state.audit_store.record,request_id,actor,roles,method,route,status_code,outcome)
    except Exception as exc:
        app.state.operations_metrics.audit_failed()
        logger.error("audit_write_failed",extra={"details":{
            "request_id":request_id,"error_type":type(exc).__name__
        }})

def install_http_middleware(app):
    @app.middleware("http")
    async def operational_boundary(request: Request,call_next):
        request_id=_request_id(request.headers)
        metrics=request.app.state.operations_metrics
        started=metrics.begin()
        decision=authorize(request.app.state.settings,request.method,request.url.path,request.headers)
        if not decision.allowed:
            response=JSONResponse({"status":"error","code":decision.code,"request_id":request_id},
                                  status_code=decision.status_code)
            route=request.url.path
            await _audit(request.app,request_id,decision,request.method,route,response.status_code,"denied")
            metrics.finish(started,response.status_code,denied=True)
            response.headers["X-Request-ID"]=request_id
            response.headers["Cache-Control"]="no-store"
            logger.info("request_denied",extra={"details":{
                "request_id":request_id,"method":request.method,"route":route,
                "status_code":response.status_code,"required_role":decision.required_role
            }})
            return response
        status_code=500
        if (request.method.upper() not in {"GET","HEAD","OPTIONS"} and
                request.app.state.settings.audit_enabled and
                request.app.state.settings.auth_mode=="proxy_headers"):
            try:
                await run_in_threadpool(request.app.state.audit_store.available)
            except Exception as exc:
                metrics.audit_failed()
                status_code=503
                metrics.finish(started,status_code)
                response=JSONResponse({"status":"error","code":"audit_unavailable","request_id":request_id},
                                      status_code=status_code)
                response.headers["X-Request-ID"]=request_id
                response.headers["Cache-Control"]="no-store"
                logger.error("audit_preflight_failed",extra={"details":{
                    "request_id":request_id,"error_type":type(exc).__name__
                }})
                return response
        try:
            response=await call_next(request)
            status_code=response.status_code
            route=_route(request)
            if request.method.upper() not in {"GET","HEAD","OPTIONS"}:
                await _audit(request.app,request_id,decision,request.method,route,status_code,
                             "allowed" if status_code<400 else "failed")
            response.headers["X-Request-ID"]=request_id
            response.headers["X-Content-Type-Options"]="nosniff"
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"]="no-store"
            return response
        finally:
            metrics.finish(started,status_code)
            logger.info("request_complete",extra={"details":{
                "request_id":request_id,"method":request.method,"route":request.url.path,
                "status_code":status_code
            }})

def websocket_authorized(ws):
    decision=authorize(ws.app.state.settings,"GET","/api/v1/ws/realtime",ws.headers)
    return decision.allowed
