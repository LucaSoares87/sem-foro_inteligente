from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.archive.store import fingerprint
from src.db import TrafficWindowRecord
from src.predictive.contracts import TrafficWindow

class HistoryIntegrityError(Exception):
    pass

class HistoryStore:
    def __init__(self,engine):
        self.engine=engine

    def save(self,window):
        payload=window.model_dump(mode="json")
        digest=fingerprint(payload)
        with Session(self.engine) as session:
            session.add(TrafficWindowRecord(source_id=window.source_id,analytics_epoch=str(window.analytics_epoch),
                start_sequence=window.start_sequence,payload=payload,digest=digest))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                row=session.scalar(select(TrafficWindowRecord).where(
                    TrafficWindowRecord.source_id==window.source_id,
                    TrafficWindowRecord.analytics_epoch==str(window.analytics_epoch),
                    TrafficWindowRecord.start_sequence==window.start_sequence))
                if row is None or row.digest!=digest or self.decode(row)!=window:
                    raise HistoryIntegrityError("conflicting history window")

    @staticmethod
    def decode(row):
        try:
            if fingerprint(row.payload)!=row.digest:
                raise ValueError
            w=TrafficWindow.model_validate(row.payload)
            if (w.source_id,str(w.analytics_epoch),w.start_sequence)!=(row.source_id,row.analytics_epoch,row.start_sequence):
                raise ValueError
            return w
        except (ValueError,TypeError) as exc:
            raise HistoryIntegrityError("invalid history") from exc

    def page(self,source,after,limit):
        with Session(self.engine) as session:
            rows=session.scalars(select(TrafficWindowRecord).where(
                TrafficWindowRecord.source_id==source,TrafficWindowRecord.id>after
                ).order_by(TrafficWindowRecord.id).limit(limit+1)).all()
            return {"items":[{"cursor":r.id,"window":self.decode(r)} for r in rows[:limit]],
                    "next_cursor":rows[min(limit,len(rows))-1].id if rows else after,"has_more":len(rows)>limit}

    def recent(self,source,epoch):
        with Session(self.engine) as session:
            rows=session.scalars(select(TrafficWindowRecord).where(
                TrafficWindowRecord.source_id==source,TrafficWindowRecord.analytics_epoch==str(epoch)
                ).order_by(TrafficWindowRecord.start_sequence.desc()).limit(60)).all()
            return [self.decode(r) for r in reversed(rows)]

    def recent_source(self,source,limit):
        with Session(self.engine) as session:
            rows=session.scalars(select(TrafficWindowRecord).where(
                TrafficWindowRecord.source_id==source
                ).order_by(TrafficWindowRecord.id.desc()).limit(limit)).all()
            return [self.decode(r) for r in reversed(rows)]
