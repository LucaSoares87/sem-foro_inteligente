from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.archive.store import fingerprint
from src.db import OptimizationExperimentRecord,QueueStateRecord
from src.optimization.contracts import OptimizationResult
from src.queueing.contracts import QueueSnapshot

class QueueIntegrityError(Exception):
    pass

class QueueStore:
    def __init__(self,engine):
        self.engine=engine

    def save(self,snapshot,result=None):
        snapshot_payload=snapshot.model_dump(mode="json")
        snapshot_digest=fingerprint(snapshot_payload)
        result_payload=result.model_dump(mode="json") if result is not None else None
        result_digest=fingerprint(result_payload) if result_payload is not None else None
        with Session(self.engine) as session:
            session.add(QueueStateRecord(source_id=snapshot.source_id,
                intersection_code=snapshot.intersection_code,queue_epoch=str(snapshot.queue_epoch),
                frame_sequence=snapshot.frame_sequence,payload=snapshot_payload,digest=snapshot_digest))
            if result is not None:
                session.add(OptimizationExperimentRecord(source_id=result.source_id,
                    intersection_code=result.intersection_code,state_sha256=result.state_sha256,
                    payload=result_payload,digest=result_digest))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing=session.scalar(select(QueueStateRecord).where(
                    QueueStateRecord.source_id==snapshot.source_id,
                    QueueStateRecord.queue_epoch==str(snapshot.queue_epoch),
                    QueueStateRecord.frame_sequence==snapshot.frame_sequence))
                if existing is None or self.decode_snapshot(existing)!=snapshot:
                    raise QueueIntegrityError("conflicting queue state")
                if result is not None:
                    experiment=session.scalar(select(OptimizationExperimentRecord).where(
                        OptimizationExperimentRecord.source_id==result.source_id,
                        OptimizationExperimentRecord.state_sha256==result.state_sha256))
                    if experiment is None or self.decode_result(experiment)!=result:
                        raise QueueIntegrityError("conflicting optimization experiment")

    @staticmethod
    def decode_snapshot(row):
        try:
            if fingerprint(row.payload)!=row.digest:
                raise ValueError
            value=QueueSnapshot.model_validate(row.payload)
            if (value.source_id,str(value.queue_epoch),value.frame_sequence)!=(row.source_id,row.queue_epoch,row.frame_sequence):
                raise ValueError
            return value
        except (ValueError,TypeError) as exc:
            raise QueueIntegrityError("invalid queue state") from exc

    @staticmethod
    def decode_result(row):
        try:
            if fingerprint(row.payload)!=row.digest:
                raise ValueError
            value=OptimizationResult.model_validate(row.payload)
            if (value.source_id,value.state_sha256)!=(row.source_id,row.state_sha256):
                raise ValueError
            return value
        except (ValueError,TypeError) as exc:
            raise QueueIntegrityError("invalid optimization experiment") from exc

    def recent_states(self,source,limit):
        with Session(self.engine) as session:
            rows=session.scalars(select(QueueStateRecord).where(
                QueueStateRecord.source_id==source).order_by(QueueStateRecord.id.desc()).limit(limit)).all()
            return [self.decode_snapshot(row) for row in reversed(rows)]

    def recent_experiments(self,source,limit):
        with Session(self.engine) as session:
            rows=session.scalars(select(OptimizationExperimentRecord).where(
                OptimizationExperimentRecord.source_id==source
                ).order_by(OptimizationExperimentRecord.id.desc()).limit(limit)).all()
            return [self.decode_result(row) for row in reversed(rows)]
