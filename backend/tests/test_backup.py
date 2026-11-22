"""Backup e restauração. SQLite usa bancos temporários próprios; PostgreSQL só roda com TEST_DATABASE_URL."""
import os
import stat
import sys

import pytest
from sqlalchemy import create_engine, text

from app.database import backup as bk
from app.database.migrate import run_migrations

needs_pg = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"),
                              reason="requer PostgreSQL em TEST_DATABASE_URL")

INSERT = ("INSERT INTO products (name, niche, description, price_cents, status, created_at) "
          "VALUES (:n, 'debt', 'd', :p, 'draft', '2026-01-01 00:00:00')")


def _names(engine) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text("SELECT name FROM products ORDER BY id"))]


@pytest.fixture()
def sqlite_db(tmp_path):
    url = f"sqlite:///{tmp_path}/live.db"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    run_migrations(eng)
    with eng.begin() as c:
        c.execute(text(INSERT), {"n": "Steady Payoff", "p": 1900})
    yield url, eng, tmp_path / "bk"
    eng.dispose()


def test_sqlite_backup_then_restore_brings_back_the_exact_data(sqlite_db):
    url, eng, out = sqlite_db
    file = bk.backup(url, out)
    assert file.exists() and file.suffix == ".sqlite"
    # estraga o banco depois do backup
    with eng.begin() as c:
        c.execute(text("DELETE FROM products"))
        c.execute(text(INSERT), {"n": "Lixo", "p": 1})
    assert _names(eng) == ["Lixo"]

    safety = bk.restore(url, file, confirmed=True)

    eng.dispose()
    assert _names(eng) == ["Steady Payoff"]  # dado original de volta
    # o estado "estragado" ficou guardado antes de ser sobrescrito
    safety_eng = create_engine(f"sqlite:///{safety}")
    assert _names(safety_eng) == ["Lixo"]
    safety_eng.dispose()


def test_restore_without_confirmation_refuses_and_changes_nothing(sqlite_db):
    url, eng, out = sqlite_db
    file = bk.backup(url, out)
    with eng.begin() as c:
        c.execute(text("DELETE FROM products"))
    with pytest.raises(bk.BackupError, match="--yes"):
        bk.restore(url, file, confirmed=False)
    assert _names(eng) == []  # nada foi sobrescrito


def test_restore_rejects_a_file_that_is_not_a_backup(sqlite_db, tmp_path):
    url, eng, _ = sqlite_db
    junk = tmp_path / "junk.sqlite"
    junk.write_bytes(b"isto nao e um banco")
    with pytest.raises(bk.BackupError):
        bk.restore(url, junk, confirmed=True)
    assert _names(eng) == ["Steady Payoff"]  # banco vivo intacto
    with pytest.raises(bk.BackupError, match="não encontrado"):
        bk.verify(url, tmp_path / "nao-existe.sqlite")


def test_restore_rejects_a_valid_sqlite_that_belongs_to_another_system(sqlite_db, tmp_path):
    """SQLite íntegro, mas sem alembic_version: restaurar apagaria o banco com dados de outro sistema."""
    import sqlite3
    url, eng, _ = sqlite_db
    foreign = tmp_path / "outro.sqlite"
    con = sqlite3.connect(foreign)
    con.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT)")
    con.commit()
    con.close()
    with pytest.raises(bk.BackupError, match="não parece um backup"):
        bk.restore(url, foreign, confirmed=True)
    assert _names(eng) == ["Steady Payoff"]  # banco vivo intacto


@pytest.mark.skipif(sys.platform.startswith("win"), reason="permissões POSIX")
def test_backup_file_is_private(sqlite_db):
    url, _, out = sqlite_db
    mode = stat.S_IMODE(bk.backup(url, out).stat().st_mode)
    assert mode == 0o600  # contém hashes de senha, auditoria e vendas


def test_postgres_password_goes_only_in_env_never_in_arguments():
    url = "postgresql+psycopg://steady:senha-secreta-xyz@db.exemplo:5433/steady"
    env, args, dbname = bk._pg_env_and_args(url)
    assert env["PGPASSWORD"] == "senha-secreta-xyz"
    assert "senha-secreta-xyz" not in " ".join(args)
    assert args == ["-h", "db.exemplo", "-p", "5433", "-U", "steady"] and dbname == "steady"


def test_cli_restore_needs_yes(sqlite_db, monkeypatch, capsys):
    url, _, out = sqlite_db
    file = bk.backup(url, out)
    monkeypatch.setattr(bk, "get_settings", lambda: type("S", (), {"database_url": url})())
    assert bk.main(["restore", str(file)]) == 1
    assert "--yes" in capsys.readouterr().err


@needs_pg
def test_postgres_backup_then_restore_round_trip(tmp_path):
    from app.database.session import engine  # já migrado pelo fixture autouse `db`
    url = engine.url.render_as_string(hide_password=False)
    with engine.begin() as c:
        c.execute(text(INSERT), {"n": "Steady Payoff", "p": 1900})
    file = bk.backup(url, tmp_path)
    assert file.suffix == ".dump"
    with engine.begin() as c:
        c.execute(text("DELETE FROM products"))
        c.execute(text(INSERT), {"n": "Lixo", "p": 1})
    safety = bk.restore(url, file, confirmed=True)
    engine.dispose()
    assert _names(engine) == ["Steady Payoff"]
    assert safety.exists()
    with engine.connect() as c:  # a versão do esquema também voltou
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
