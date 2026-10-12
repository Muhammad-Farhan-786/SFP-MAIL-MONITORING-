from alembic import context
from app.db import engine, Base
from app import models

if context.is_offline_mode():
    from app.config import config

    context.configure(
        url=config().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
