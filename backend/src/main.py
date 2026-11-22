from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from src.config import Settings
from src.db import make_engine, readiness

log = logging.getLogger(__name__)

def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings()
        app.state.engine = make_engine(app.state.settings)
        app.state.ws_count = 0
        try:
            yield
        finally:
            await run_in_threadpool(app.state.engine.dispose)

    app = FastAPI(title="Semáforos Inteligentes", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.error("Internal failure: %s", type(exc).__name__)
        return JSONResponse({"status":"error","code":"INTERNAL_SERVER_ERROR"}, status_code=500)

    @app.get("/health/live")
    async def live():
        return {"status":"alive"}

    @app.get("/health")
    @app.get("/api/v1/health")
    async def health(request: Request):
        database, schema = await run_in_threadpool(readiness, request.app.state.engine)
        ready = database == "online" and schema == "current"
        return JSONResponse({
            "status": "ready" if ready else "degraded",
            "backend": "online", "database": database, "schema": schema,
            "websocket": "available", "websocket_connections": request.app.state.ws_count,
            "stream_manager": "not_implemented", "inference_engine": "not_loaded",
            "operation_mode": request.app.state.settings.operation_mode,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status_code=200 if ready else 503)

    @app.websocket("/api/v1/ws/realtime")
    async def realtime(ws: WebSocket):
        origins = {x.strip() for x in ws.app.state.settings.allowed_origins.split(",") if x.strip()}
        origin = ws.headers.get("origin")
        # Browser sessions require an allowlisted origin; native clients have no Origin.
        if origin and origin not in origins:
            await ws.close(code=1008)
            return
        if ws.app.state.ws_count >= 50:
            await ws.close(code=1013)
            return
        ws.app.state.ws_count += 1
        try:
            await ws.accept()
            await asyncio.wait_for(ws.send_json({"version":1,"type":"connection_ack"}),5)
            while True:
                message = await asyncio.wait_for(ws.receive_text(),35)
                if message != "ping":
                    await ws.close(code=1008)
                    break
                await asyncio.wait_for(ws.send_json({"version":1,"type":"heartbeat","timestamp":datetime.now(timezone.utc).isoformat()}),5)
        except WebSocketDisconnect:
            pass
        except TimeoutError:
            try:
                await ws.close(code=1001)
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            ws.app.state.ws_count -= 1
    return app

app = create_app()
