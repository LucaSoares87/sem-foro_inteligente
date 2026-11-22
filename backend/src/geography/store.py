from sqlalchemy import select
from sqlalchemy.orm import Session
from src.db import Intersection

class GeographyStore:
    def __init__(self,engine):
        self.engine=engine

    def sync(self,entries):
        with Session(self.engine) as session:
            for entry in entries:
                row=session.get(Intersection,entry.code)
                values={"name":entry.name,"district":entry.district,"latitude":entry.latitude,
                        "longitude":entry.longitude,"enabled":entry.enabled}
                if row is None:
                    session.add(Intersection(code=entry.code,configuration={},**values))
                else:
                    for key,value in values.items():
                        setattr(row,key,value)
            session.commit()

    def list(self,include_disabled=False,district=None,with_coordinates=None):
        statement=select(Intersection)
        if not include_disabled:
            statement=statement.where(Intersection.enabled.is_(True))
        if district is not None:
            statement=statement.where(Intersection.district==district)
        if with_coordinates is True:
            statement=statement.where(Intersection.latitude.is_not(None),Intersection.longitude.is_not(None))
        elif with_coordinates is False:
            statement=statement.where(Intersection.latitude.is_(None),Intersection.longitude.is_(None))
        with Session(self.engine) as session:
            return list(session.scalars(statement.order_by(Intersection.code)).all())

    def get(self,code,include_disabled=False):
        with Session(self.engine) as session:
            row=session.get(Intersection,code)
            if row is None or (not include_disabled and not row.enabled):
                return None
            return row
