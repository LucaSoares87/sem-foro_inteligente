import os
from uuid import uuid4
import pytest
from sqlalchemy import delete
from src.db import make_engine,TrafficWindowRecord
from src.config import Settings
from src.predictive.store import HistoryStore
from test_predictive import make_windows

@pytest.mark.skipif(os.getenv("ARCHIVE_POSTGRES_TEST")!="1",reason="requires migrated disposable CI PostgreSQL")
def test_history_postgres():
    engine=make_engine(Settings())
    source="CI_"+uuid4().hex
    w=make_windows(1)[0].model_copy(update={"source_id":source})
    try:
        store=HistoryStore(engine)
        store.save(w)
        store.save(w)
        assert HistoryStore(engine).recent(source,w.analytics_epoch)==[w]
    finally:
        with engine.begin() as conn:
            conn.execute(delete(TrafficWindowRecord).where(TrafficWindowRecord.source_id==source))
        engine.dispose()
