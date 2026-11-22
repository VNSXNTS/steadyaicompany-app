"""Testes das migrações Alembic. Cada teste usa um banco SQLite temporário PRÓPRIO (não o dos outros testes)."""
import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.database.migrate import downgrade, run_migrations
from app.database.session import Base
from app.models import entities  # noqa: F401

APP_TABLES = {
    "agents", "audit_logs", "expenses", "login_attempts", "products", "users", "auth_sessions",
    "sales", "tasks", "ai_usage", "approvals", "task_logs",
}
NEW_IN_AUTH = {"users", "auth_sessions", "login_attempts"}


@pytest.fixture()
def fresh_engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/m.db", connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


def _tables(eng) -> set[str]:
    return set(inspect(eng).get_table_names())


def _version(eng) -> str | None:
    with eng.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_upgrade_on_empty_database_creates_every_table(fresh_engine):
    run_migrations(fresh_engine)
    assert _tables(fresh_engine) == APP_TABLES | {"alembic_version"}
    assert _version(fresh_engine) == "0001"


def test_migrated_schema_matches_the_models_exactly(fresh_engine):
    """Se alguém mudar um modelo sem criar migração, este teste falha (deriva de esquema)."""
    run_migrations(fresh_engine)
    with fresh_engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], f"modelos e migrações divergem: {diff}"


def test_upgrade_twice_is_a_noop(fresh_engine):
    run_migrations(fresh_engine)
    with fresh_engine.begin() as c:
        c.execute(text("INSERT INTO products (name, niche, description, price_cents, status, created_at) "
                       "VALUES ('p','n','d',100,'draft','2026-01-01 00:00:00')"))
    run_migrations(fresh_engine)
    with fresh_engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM products")).scalar() == 1
    assert _version(fresh_engine) == "0001"


def test_adopts_a_v02_database_created_by_create_all_without_losing_data(fresh_engine):
    """Banco da v0.2: tabelas sem Alembic e sem as tabelas de autenticação, com dados reais."""
    Base.metadata.create_all(fresh_engine)
    with fresh_engine.begin() as c:
        for t in NEW_IN_AUTH:
            c.execute(text(f"DROP TABLE {t}"))
        c.execute(text("INSERT INTO products (name, niche, description, price_cents, status, created_at) "
                       "VALUES ('Steady Payoff','debt','d',1900,'draft','2026-01-01 00:00:00')"))
        c.execute(text("INSERT INTO expenses (category, description, amount_cents, created_at) "
                       "VALUES ('ai','teste',250,'2026-01-01 00:00:00')"))
    assert "alembic_version" not in _tables(fresh_engine)
    assert not NEW_IN_AUTH & _tables(fresh_engine)

    run_migrations(fresh_engine)

    assert _tables(fresh_engine) == APP_TABLES | {"alembic_version"}  # só faltavam as de autenticação
    with fresh_engine.connect() as c:
        assert c.execute(text("SELECT name, price_cents FROM products")).one() == ("Steady Payoff", 1900)
        assert c.execute(text("SELECT amount_cents FROM expenses")).scalar() == 250


def test_downgrade_to_base_removes_everything_and_upgrade_recreates(fresh_engine):
    run_migrations(fresh_engine)
    downgrade(fresh_engine, "base")
    assert _tables(fresh_engine) <= {"alembic_version"}
    run_migrations(fresh_engine)
    assert _tables(fresh_engine) == APP_TABLES | {"alembic_version"}


# --- só com PostgreSQL real (TEST_DATABASE_URL=postgresql+psycopg://...) -------------------------------
needs_pg = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"),
                              reason="requer PostgreSQL em TEST_DATABASE_URL")


@needs_pg
def test_postgres_migrated_schema_matches_the_models_exactly():
    from app.database.session import engine  # já migrado pelo fixture autouse `db`
    assert engine.dialect.name == "postgresql"
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"modelos e migrações divergem no PostgreSQL: {diff}"


@needs_pg
def test_postgres_downgrade_and_upgrade_round_trip():
    from app.database.session import engine
    downgrade(engine, "base")
    assert _tables(engine) <= {"alembic_version"}
    run_migrations(engine)
    assert _tables(engine) == APP_TABLES | {"alembic_version"}
