from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
import json
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.archive.contracts import ArchivedRun
from src.db import PipelineArchive
from src.ingestion.engine import DuplicateConflict

class ArchiveIntegrityError(Exception):
    pass

def fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False).encode("utf-8")
    return sha256(encoded).hexdigest()

class ArchiveStore:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _decode(row):
        try:
            if not compare_digest(fingerprint(row.payload), row.digest):
                raise ValueError("digest mismatch")
            run = ArchivedRun.model_validate(row.payload)
            observation = run.report.observation
            if (str(observation.event_id), observation.intersection_code, observation.origin) != (
                row.event_id, row.intersection_code, row.origin
            ):
                raise ValueError("index mismatch")
            return run
        except (ValueError, TypeError, KeyError) as exc:
            raise ArchiveIntegrityError("invalid archive record") from exc

    def get(self, event_id: UUID):
        with Session(self.engine) as session:
            row = session.scalar(select(PipelineArchive).where(PipelineArchive.event_id == str(event_id)))
            return self._decode(row) if row is not None else None

    def save(self, run: ArchivedRun):
        observation = run.report.observation
        payload = run.model_dump(mode="json")
        ArchivedRun.model_validate(payload)
        with Session(self.engine) as session:
            session.add(PipelineArchive(event_id=str(observation.event_id),
                intersection_code=observation.intersection_code, origin=observation.origin,
                payload=payload, digest=fingerprint(payload)))
            try:
                session.commit()
                return run
            except IntegrityError:
                session.rollback()
        existing = self.get(observation.event_id)
        if existing is None:
            raise ArchiveIntegrityError("archive write rejected")
        if existing.report.observation != observation:
            raise DuplicateConflict
        return existing

    def page(self, after: int, limit: int, intersection: str | None = None):
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError("invalid pagination")
        statement = select(PipelineArchive).where(PipelineArchive.id > after)
        if intersection is not None:
            statement = statement.where(PipelineArchive.intersection_code == intersection)
        with Session(self.engine) as session:
            rows = session.scalars(statement.order_by(PipelineArchive.id).limit(limit+1)).all()
            items = []
            for row in rows[:limit]:
                run = self._decode(row)
                items.append({"cursor":row.id,"event_id":row.event_id,
                              "intersection_code":row.intersection_code,
                              "origin":row.origin,"state":run.report.state,
                              "finished_at":run.report.finished_at})
            return {"items":items,"next_cursor":items[-1]["cursor"] if items else after,
                    "has_more":len(rows)>limit}

    def retention(self, cutoff: datetime, *, apply: bool = False):
        if cutoff.tzinfo is None:
            raise ValueError("cutoff requires timezone")
        with Session(self.engine) as session:
            criteria = PipelineArchive.created_at < cutoff
            if not apply:
                return session.scalar(select(func.count()).select_from(PipelineArchive).where(criteria))
            result = session.execute(delete(PipelineArchive).where(criteria))
            session.commit()
            return result.rowcount
