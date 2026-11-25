"""Alembic environment for V1 file-backed SQLite databases."""

from alembic import context

from redteam.persistence.database import create_sqlite_engine
from redteam.persistence.models import Base


def run_migrations_offline() -> None:
    context.configure(
        dialect_name="sqlite",
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    database_path = context.get_x_argument(as_dictionary=True).get("database_path")
    if database_path is None:
        database_path = context.config.get_main_option("database_path")
    if not database_path:
        raise ValueError("Set database_path in alembic.ini or pass -x database_path=PATH.")

    engine = create_sqlite_engine(database_path)
    try:
        # The outer transaction commits the schema changes and revision together.
        with engine.begin() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
