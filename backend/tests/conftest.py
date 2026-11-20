import os
import tempfile

# Precisa vir antes de importar o app: o banco e as chaves são lidos no import.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_API_KEY"] = "test-key"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MAX_TASK_ATTEMPTS"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import entities  # noqa: E402,F401
from app.services.agent_registry import seed_agents  # noqa: E402


@pytest.fixture(autouse=True)
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_agents(session)
        yield session


@pytest.fixture()
def client(db):
    with TestClient(app, headers={"X-API-Key": "test-key"}) as c:
        yield c
