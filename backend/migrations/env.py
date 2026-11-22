"""Ambiente do Alembic. A URL vem de DATABASE_URL (via app.core.config); nunca fica no repositório."""
from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.database.session import Base
from app.models import entities  # noqa: F401  (registra os modelos em Base.metadata)

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Permite que o código (run_migrations) injete um engine; senão usa DATABASE_URL.
    return config.attributes.get("url") or get_settings().database_url


def run_migrations_offline() -> None:
    url = _url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=url.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:
        _run(connectable)
        return
    url = _url()
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=args)
    with engine.connect() as connection:
        _run(connection)
    engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
