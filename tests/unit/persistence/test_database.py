"""Verify the SQLite factories and Alembic baseline with isolated databases."""

from argparse import Namespace
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from redteam.persistence.database import create_session_factory, create_sqlite_engine


ALEMBIC_CONFIG = Path(__file__).resolve().parents[3] / "alembic.ini"


@pytest.fixture
def engine(tmp_path):
    database = create_sqlite_engine(tmp_path / "子目录" / "test database.sqlite3")
    yield database
    database.dispose()


def test_sessions_commit_and_rollback_with_foreign_keys_enabled(engine):
    sessions = create_session_factory(engine)
    path = Path(engine.url.database)
    assert path.parent.is_dir()
    with sessions.begin() as session:
        session.execute(text("CREATE TABLE fixture (value INTEGER NOT NULL)"))
        session.execute(text("INSERT INTO fixture (value) VALUES (1)"))

    with sessions() as session:
        session.execute(text("INSERT INTO fixture (value) VALUES (2)"))
    with sessions() as session:
        assert session.scalars(text("SELECT value FROM fixture")).all() == [1]

    with engine.connect() as first, engine.connect() as second:
        assert first.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert second.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    assert path.is_file()


def test_alembic_upgrade_downgrade_and_reupgrade(tmp_path):
    path = tmp_path / "isolated" / "baseline.sqlite3"
    config = Config(str(ALEMBIC_CONFIG), cmd_opts=Namespace(x=[f"database_path={path}"]))

    command.upgrade(config, "head")
    assert path.is_file()
    engine = create_sqlite_engine(path)
    try:
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == "0001"
            assert inspect(connection).get_table_names() == ["alembic_version"]

        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() is None

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == "0001"
    finally:
        engine.dispose()


def test_offline_migration_generates_sql_without_creating_database(tmp_path):
    path = tmp_path / "offline.sqlite3"
    output = StringIO()
    config = Config(
        str(ALEMBIC_CONFIG), output_buffer=output,
        cmd_opts=Namespace(x=[f"database_path={path}"]),
    )

    command.upgrade(config, "head", sql=True)

    assert "CREATE TABLE alembic_version" in output.getvalue()
    assert "'0001'" in output.getvalue()
    assert not path.exists()
