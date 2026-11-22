from datetime import datetime
from sqlalchemy import DateTime, String, JSON, ForeignKey, CheckConstraint, Float, text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import create_engine

SCHEMA_REVISION = "0001_foundation"

class Base(DeclarativeBase):
    pass

class Intersection(Base):
    __tablename__ = "intersections"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (CheckConstraint("confidence >= 0 AND confidence <= 1"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    intersection_code: Mapped[str] = mapped_column(ForeignKey("intersections.code"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

def make_engine(settings):
    url = settings.db_url()
    options = {"pool_pre_ping": True}
    if url.get_backend_name() == "postgresql":
        options.update(connect_args={"connect_timeout": 2,"options": "-c statement_timeout=2000"}, pool_timeout=2)
    return create_engine(url, **options)

def readiness(engine):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        return "online", "current" if revisions == [SCHEMA_REVISION] else "outdated"
    except Exception:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return "online", "unverified"
        except Exception:
            return "offline", "unverified"
