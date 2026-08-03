from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config
fileConfig(config.config_file_name)


def get_engine():
    return current_app.extensions["migrate"].db.engine


def get_metadata():
    return current_app.extensions["migrate"].db.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url).replace("%", "%%"),
        target_metadata=get_metadata(),
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
