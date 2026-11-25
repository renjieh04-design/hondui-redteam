"""Connection and session factories for the V1 SQLite database."""

from contextlib import closing
from pathlib import Path
from sqlite3 import Connection

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _enable_foreign_keys(connection: Connection, _connection_record: object) -> None:
    # SQLite ignores this pragma inside a transaction.
    previous = connection.autocommit
    connection.autocommit = True
    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        connection.autocommit = previous


def create_sqlite_engine(database_path: str | Path) -> Engine:
    """Create an engine for a local database file at the supplied path."""
    path = Path(database_path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        connect_args={"autocommit": False},
    )
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Bind a session factory to the given engine without opening a session."""
    return sessionmaker(bind=engine)
