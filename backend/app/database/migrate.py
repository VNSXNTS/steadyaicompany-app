"""Executa as migrações Alembic no startup e expõe utilidades para testes e CLI.

Decisão (Fase 3): o esquema é criado SÓ por migrações. O banco é a fonte de verdade da versão
(tabela alembic_version). Instância única: não há trava entre processos, então não suba duas
réplicas migrando o mesmo banco ao mesmo tempo (ver docs/BANCO.md).
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def run_migrations(engine: Engine, revision: str = "head") -> None:
    """Sobe o esquema até `revision` usando a conexão do próprio engine da aplicação."""
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)


def downgrade(engine: Engine, revision: str) -> None:
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, revision)
