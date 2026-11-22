from datetime import datetime
from sqlalchemy import BigInteger, UniqueConstraint, DateTime, String, JSON, ForeignKey, CheckConstraint, Float, text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import create_engine

SCHEMA_REVISION = "0004_intersection_geography"

class Base(DeclarativeBase):
    pass

class Intersection(Base):
    __tablename__ = "intersections"
    __table_args__ = (
        CheckConstraint("(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)", name="ck_intersection_coordinate_pair"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_intersection_latitude"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_intersection_longitude"),
    )
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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

class PipelineArchive(Base):
    __tablename__ = "pipeline_archive"
    __table_args__ = (CheckConstraint("origin = 'synthetic'", name="ck_pipeline_archive_origin"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    intersection_code: Mapped[str] = mapped_column(String(80), index=True)
    origin: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class TrafficWindowRecord(Base):
    __tablename__ = "traffic_windows"
    __table_args__ = (UniqueConstraint("source_id","analytics_epoch","start_sequence",name="uq_traffic_window"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80),index=True)
    analytics_epoch: Mapped[str] = mapped_column(String(36))
    start_sequence: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
