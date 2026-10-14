from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import config


class Base(DeclarativeBase):
    pass


engine = create_engine(config().database_url, pool_pre_ping=True, hide_parameters=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with Session() as session:
        yield session


def insert_once(db, table, values, keys):
    """Atomic first-row initialization; safe when API and scheduler arrive together."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(table).values(**values).on_conflict_do_nothing(index_elements=keys)
    )
