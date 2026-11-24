from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from src.config import Settings
from src.db import make_engine, readiness
from src.ingestion.engine import IngestionEngine
from src.ingestion.routes import router as ingestion_router
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.routes import router as pipeline_router
from src.archive.store import ArchiveStore
from src.archive.service import ArchiveService
from src.archive.routes import router as archive_router
from src.video.contracts import load_sources
from src.video.manager import VideoManager
from src.video.routes import router as video_router
from src.vision.contracts import ModelSpec
from src.vision.service import VisionService
from src.vision.routes import router as vision_router
from src.tracking.service import TrackingService
from src.tracking.routes import router as tracking_router
from src.analytics.contracts import load_geometry
from src.analytics.service import AnalyticsService
from src.analytics.routes import router as analytics_router
from src.predictive.store import HistoryStore
from src.predictive.service import HistoryService
from src.predictive.routes import router as predictive_router
from src.decision.routes import router as decision_router
from src.decision.service import status as decision_status
from src.geography.contracts import load_registry
from src.geography.routes import router as geography_router
from src.geography.service import GeographyService
from src.geography.store import GeographyStore
from src.operations.audit import AuditStore
from src.operations.http import install_http_middleware, websocket_authorized
from src.operations.metrics import OperationsMetrics
from src.operations.routes import router as operations_router
from src.operations.security import security_status
from src.validation.contracts import load_evidence
from src.validation.routes import router as validation_router
from src.validation.service import ValidationService

log = logging.getLogger(__name__)

def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings()
        app.state.video = VideoManager(load_sources(app.state.settings.video_sources_json.get_secret_value()), app.state.settings.video_root)
        model_json = app.state.settings.vision_model_json
        try:
            spec = ModelSpec.model_validate_json(model_json.get_secret_value()) if model_json and model_json.get_secret_value() else None
            invalid_model = False
        except ValueError:
            spec, invalid_model = None, True
        app.state.vision = VisionService(app.state.video,spec,app.state.settings.vision_model_root)
        app.state.tracking = TrackingService(app.state.vision)
        app.state.vision.tracking = app.state.tracking
        try:
            geometry = load_geometry(app.state.settings.traffic_geometry_json.get_secret_value(),
                {k:s.spec.intersection_code for k,s in app.state.video.sessions.items()})
            invalid_geometry = False
        except ValueError:
            geometry, invalid_geometry = {}, True
        app.state.analytics = AnalyticsService(app.state.tracking,geometry,invalid_geometry)
        app.state.tracking.analytics = app.state.analytics
        if invalid_model:
            app.state.vision.state, app.state.vision.error = "error", "model_config_invalid"
        app.state.engine = make_engine(app.state.settings)
        app.state.audit_store = AuditStore(app.state.engine)
        try:
            validation_evidence = load_evidence(app.state.settings.validation_evidence_json.get_secret_value())
            validation_error = None
        except ValueError:
            validation_evidence, validation_error = (), "validation_evidence_invalid"
        app.state.validation = ValidationService(app.state.video, app.state.vision, validation_evidence, validation_error)
        app.state.geography = GeographyService(GeographyStore(app.state.engine))
        raw_registry = app.state.settings.intersection_registry_json.get_secret_value()
        try:
            registry = load_registry(raw_registry)
            app.state.geography.configured = len(registry)
            if registry:
                database_state, schema_state = await run_in_threadpool(readiness, app.state.engine)
                if database_state == "online" and schema_state == "current":
                    await run_in_threadpool(app.state.geography.sync, registry)
                else:
                    app.state.geography.error = "schema_not_ready"
        except ValueError:
            app.state.geography.error = "registry_config_invalid"
        app.state.history = HistoryService(HistoryStore(app.state.engine),app.state.settings.durable_archive)
        app.state.analytics.history = app.state.history
        app.state.ws_count = 0
        app.state.pipeline = PipelineOrchestrator()
        app.state.archive = ArchiveService(ArchiveStore(app.state.engine), app.state.settings.durable_archive)
        async def process(observation):
            return await app.state.archive.process(observation, app.state.pipeline, app.state.ingestion)
        app.state.ingestion = IngestionEngine(processor=process, timeout=8.0 if app.state.archive.enabled else 1.0)
        try:
            app.state.ingestion.start()
            app.state.history.start()
            app.state.vision.start()
            yield
        finally:
            try:
                try:
                    try:
                        await app.state.vision.shutdown()
                    finally:
                        await app.state.video.shutdown()
                finally:
                    await app.state.ingestion.stop()
            finally:
                try:
                    await app.state.history.stop()
                finally:
                    await run_in_threadpool(app.state.engine.dispose)

    app = FastAPI(title="Semáforos Inteligentes", version="0.1.0", lifespan=lifespan)
    app.state.operations_metrics = OperationsMetrics()
    install_http_middleware(app)

    app.include_router(ingestion_router)
    app.include_router(pipeline_router)
    app.include_router(archive_router)
    app.include_router(video_router)
    app.include_router(vision_router)
    app.include_router(tracking_router)
    app.include_router(analytics_router)
    app.include_router(predictive_router)
    app.include_router(decision_router)
    app.include_router(geography_router)
    app.include_router(operations_router)
    app.include_router(validation_router)

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
        geography = request.app.state.geography.status()
        ready = database == "online" and schema == "current" and geography["state"] != "error"
        vision = request.app.state.vision.status()
        video = request.app.state.video.status()
        video["inference_connected"] = vision["state"] == "ready"
        return JSONResponse({
            "status": "ready" if ready else "degraded",
            "backend": "online", "database": database, "schema": schema,
            "websocket": "available", "websocket_connections": request.app.state.ws_count,
            "stream_manager": video["state"], "inference_engine": vision["state"],
            "video": video, "vision": vision,
            "tracking": request.app.state.tracking.status(),
            "analytics": request.app.state.analytics.status(),
            "predictive": request.app.state.history.status(),
            "decision": decision_status(),
            "geography": geography,
            "operations": {
                "security": security_status(request.app.state.settings),
                "audit_enabled": request.app.state.settings.audit_enabled,
                "metrics": request.app.state.operations_metrics.snapshot()
            },
            "validation": request.app.state.validation.health_status(),
            "ingestion": request.app.state.ingestion.status(),
            "pipeline": request.app.state.pipeline.status(),
            "archive": request.app.state.archive.status(database, schema),
            "operation_mode": request.app.state.settings.operation_mode,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status_code=200 if ready else 503)

    @app.websocket("/api/v1/ws/realtime")
    async def realtime(ws: WebSocket):
        if not websocket_authorized(ws):
            await ws.close(code=1008)
            return
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
