from datetime import datetime, timezone
from time import monotonic
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from src.archive.contracts import ArchivedRun
from src.archive.store import ArchiveIntegrityError
from src.ingestion.contracts import Handoff, Receipt

class ArchiveUnavailable(Exception):
    pass

class ArchiveService:
    def __init__(self, store, enabled: bool):
        self.store = store
        self.enabled = enabled

    async def lookup(self, event_id):
        if not self.enabled:
            return None
        return await self.execute(self.store.get, event_id)

    async def execute(self, action, *args):
        if not self.enabled:
            raise ArchiveUnavailable("archive disabled")
        try:
            return await run_in_threadpool(action, *args)
        except (SQLAlchemyError, ArchiveIntegrityError) as exc:
            raise ArchiveUnavailable("archive unavailable") from exc

    async def process(self, observation, pipeline, ingestion):
        if not self.enabled:
            return await pipeline.process(observation)
        previous = await self.lookup(observation.event_id)
        if previous is not None:
            from src.ingestion.engine import DuplicateConflict
            if previous.report.observation != observation:
                raise DuplicateConflict
            return Handoff(observation=observation)
        start = monotonic()
        cursor = pipeline.events.status()["published"]
        handoff = await pipeline.process(observation)
        report = pipeline.get(observation.event_id)
        events = pipeline.events.read(cursor, 100)["events"]
        pending = ingestion.get(observation.event_id)
        receipt = Receipt(observation=observation, state="processed",
                          accepted_at=pending.accepted_at,
                          finished_at=datetime.now(timezone.utc),
                          processing_ms=(monotonic()-start)*1000)
        await self.execute(self.store.save, ArchivedRun(receipt=receipt,report=report,events=tuple(events)))
        return handoff

    def status(self, database, schema):
        return {"enabled":self.enabled,
                "status":"disabled" if not self.enabled else
                   "available" if database=="online" and schema=="current" else "unavailable",
                "scope":"completed_synthetic_runs",
                "durable_queue":False}
