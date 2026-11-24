from sqlalchemy import select
from sqlalchemy.orm import Session
from src.db import OperationalAuditEvent

class AuditStore:
    def __init__(self,engine):
        self.engine=engine

    def available(self):
        with Session(self.engine) as session:
            session.execute(select(OperationalAuditEvent.id).limit(1)).all()
        return True

    def record(self,request_id,actor,roles,method,route,status_code,outcome):
        row=OperationalAuditEvent(
            request_id=request_id,actor=actor,roles=",".join(sorted(roles)),
            method=method[:8],route=route[:200],status_code=int(status_code),outcome=outcome[:40])
        with Session(self.engine) as session:
            session.add(row)
            session.commit()

    def page(self,after,limit):
        with Session(self.engine) as session:
            rows=session.scalars(select(OperationalAuditEvent).where(
                OperationalAuditEvent.id>after
            ).order_by(OperationalAuditEvent.id).limit(limit+1)).all()
            items=[{
                "cursor":row.id,"request_id":row.request_id,"actor":row.actor,
                "roles":[x for x in row.roles.split(",") if x],
                "method":row.method,"route":row.route,"status_code":row.status_code,
                "outcome":row.outcome,"created_at":row.created_at,
            } for row in rows[:limit]]
            return {"items":items,"next_cursor":items[-1]["cursor"] if items else after,"has_more":len(rows)>limit}
