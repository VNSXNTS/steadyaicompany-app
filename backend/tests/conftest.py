import os
import tempfile

# Precisa vir antes de importar o app: o banco e as chaves são lidos no import.
_tmp = tempfile.mkdtemp()
# TEST_DATABASE_URL (opt-in explícito) permite rodar a suíte em PostgreSQL. DATABASE_URL de propósito
# NÃO é lido aqui: o fixture abaixo apaga todas as tabelas, e um DATABASE_URL real no shell seria destruído.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_API_KEY"] = "test-key"
os.environ["OWNER_EMAIL"] = "owner@example.com"
os.environ["OWNER_PASSWORD"] = "test-password"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MAX_TASK_ATTEMPTS"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import text  # noqa: E402

from app.database.migrate import run_migrations  # noqa: E402
from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import entities  # noqa: E402,F401
from app.services.agent_registry import seed_agents  # noqa: E402


@pytest.fixture(autouse=True)
def db():
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    run_migrations(engine)  # o esquema dos testes vem das migrações, não de create_all
    with SessionLocal() as session:
        seed_agents(session)
        yield session


@pytest.fixture()
def client(db):
    with TestClient(app, headers={"X-API-Key": "test-key"}) as c:
        yield c
