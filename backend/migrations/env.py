from alembic import context
from sqlalchemy import create_engine, pool
from src.config import Settings
from src.db import Base

url = Settings().db_url()
if context.is_offline_mode():
    context.configure(url=url.render_as_string(hide_password=False), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
