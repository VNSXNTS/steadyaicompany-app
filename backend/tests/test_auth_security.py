"""Testes de segurança do login. Cada teste protege uma regra e deve falhar se ela for quebrada
(verificado por mutação manual; ver descrição do PR)."""
import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.database.session import engine
from app.main import app
from app.models.entities import AuditLog, AuthSession, User
from app.services.auth import LOGIN_MAX_FAILURES, SESSION_COOKIE, ensure_owner_account

OWNER = "owner@example.com"
PASSWORD = "test-password"  # definido em conftest.py (OWNER_PASSWORD)
WRONG = "wrong-password-xyz-123"
BAD_ENDPOINTS = ["/agents", "/tasks", "/dashboard", "/settings", "/approvals", "/auth/me"]


def _login(c: TestClient, password: str = PASSWORD, email: str = OWNER):
    return c.post("/auth/login", json={"email": email, "password": password})


class _Capture(logging.Handler):
    """Handler ligado direto ao logger 'steady' (propagate=False, então o caplog da raiz não o enxerga)."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture()
def app_logs():
    handler = _Capture()
    logger = logging.getLogger("steady")
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(previous)


# 1. senha só como hash -------------------------------------------------------------------------
def test_password_is_stored_only_as_hash(db):
    with TestClient(app):
        pass  # o startup cria a conta proprietária
    user = db.query(User).one()
    assert user.password_hash != PASSWORD
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")
    # a senha em texto puro não pode estar em NENHUMA coluna de NENHUMA tabela
    insp = inspect(engine)
    with engine.connect() as conn:
        for table in insp.get_table_names():
            for row in conn.execute(text(f'SELECT * FROM "{table}"')).fetchall():
                assert PASSWORD not in json.dumps([str(v) for v in row]), f"senha em texto puro em {table}"


# 2. cookie ---------------------------------------------------------------------------------------
def test_session_cookie_is_httponly_and_samesite_strict():
    with TestClient(app) as c:
        header = _login(c).headers["set-cookie"]
        assert header.startswith(f"{SESSION_COOKIE}=")
        attrs = [a.strip().lower() for a in header.split(";")]
        assert "httponly" in attrs
        assert "samesite=strict" in attrs
        assert any(a.startswith("max-age=") for a in attrs)  # sessão com validade


# 3. bloqueio por tentativas --------------------------------------------------------------------
def test_login_is_blocked_after_max_failures_even_with_correct_password():
    with TestClient(app) as c:
        for _ in range(LOGIN_MAX_FAILURES):
            assert _login(c, WRONG).status_code == 401
        blocked = _login(c, PASSWORD)  # senha CERTA, mas o IP já está bloqueado
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert SESSION_COOKIE not in blocked.headers.get("set-cookie", "")


# 4. auditoria ------------------------------------------------------------------------------------
def test_login_is_audited_without_password(db):
    with TestClient(app) as c:
        assert _login(c, WRONG).status_code == 401
        c.headers["X-CSRF-Token"] = _login(c, PASSWORD).json()["csrf_token"]
        c.post("/auth/logout")
        # usuário digitando a senha no campo de e-mail: também não pode ir para a auditoria
        _login(c, email="digitei-a-senha-aqui-XYZ789@example.com")
    rows = db.query(AuditLog).filter(AuditLog.action.like("auth.%")).all()
    actions = {r.action for r in rows}
    assert {"auth.login_failed", "auth.login_success", "auth.logout"} <= actions
    blob = json.dumps([[r.actor, r.action, r.detail] for r in rows], default=str)
    for secret in (PASSWORD, WRONG, "XYZ789"):
        assert secret not in blob


# 5. rota protegida sem sessão ------------------------------------------------------------------
@pytest.mark.parametrize("path", BAD_ENDPOINTS)
def test_protected_route_without_session_is_401(path):
    with TestClient(app) as anon:  # sem X-API-Key e sem cookie
        assert anon.get(path).status_code == 401
        anon.cookies.set(SESSION_COOKIE, "token-inventado")
        assert anon.get(path).status_code == 401  # cookie falso também


def test_health_stays_public():
    with TestClient(app) as anon:
        assert anon.get("/health").status_code == 200


# 6. logout ---------------------------------------------------------------------------------------
def test_logout_invalidates_the_session_token_server_side(db):
    with TestClient(app) as c:
        c.headers["X-CSRF-Token"] = _login(c).json()["csrf_token"]
        token = c.cookies.get(SESSION_COOKIE)
        assert token and c.get("/auth/me").status_code == 200
        assert db.query(AuthSession).count() == 1
        c.post("/auth/logout")
    assert db.query(AuthSession).count() == 0
    # reapresenta o token ANTIGO num cliente novo: o servidor tem de recusar
    with TestClient(app) as replay:
        replay.cookies.set(SESSION_COOKIE, token)
        assert replay.get("/auth/me").status_code == 401
        assert replay.get("/agents").status_code == 401


# 7. X-API-Key desligada por padrão -------------------------------------------------------------
def test_api_key_is_off_by_default(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    from app.core.config import get_settings

    assert get_settings().admin_api_key == ""
    with TestClient(app) as c:
        for key in ("test-key", "", "qualquer-coisa", "troque-por-uma-chave-longa-e-aleatoria"):
            assert c.get("/agents", headers={"X-API-Key": key}).status_code == 401
        assert _login(c).status_code == 200  # o login real continua valendo
        assert c.get("/agents").status_code == 200


def test_without_any_credentials_configured_everything_is_refused(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("OWNER_EMAIL", raising=False)
    monkeypatch.delenv("OWNER_PASSWORD", raising=False)
    with TestClient(app) as c:
        assert c.get("/agents", headers={"X-API-Key": "test-key"}).status_code == 503
        assert _login(c).status_code == 401


def test_env_example_has_no_default_secrets():
    text_ = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    values = dict(re.findall(r"^([A-Z_]+)=(.*)$", text_, flags=re.M))
    for name in ("ADMIN_API_KEY", "POSTGRES_PASSWORD", "OWNER_PASSWORD"):
        assert name in values, f"{name} não está documentada no .env.example"
        assert values[name].strip() == "", f"{name} deve ficar vazia no .env.example"
    assert "OWNER_EMAIL" in values and "AUTH_COOKIE_SECURE" in values


# nada de senha padrão ----------------------------------------------------------------------------
def test_no_default_password_without_owner_env(monkeypatch, db):
    monkeypatch.delenv("OWNER_EMAIL", raising=False)
    monkeypatch.delenv("OWNER_PASSWORD", raising=False)
    db.query(User).delete()
    db.commit()
    ensure_owner_account(db)
    assert db.query(User).count() == 0


# 8. senha fora dos logs --------------------------------------------------------------------------
def test_login_password_never_appears_in_any_log(app_logs, caplog):
    from app.core.logging import JsonFormatter

    caplog.set_level(logging.DEBUG)
    with TestClient(app) as c:
        _login(c, WRONG)                                  # falha
        c.headers["X-CSRF-Token"] = _login(c, PASSWORD).json()["csrf_token"]  # sucesso
        c.post("/auth/logout")
        _login(c, "x" * 2000)                             # 422 (senha grande demais)
        for _ in range(LOGIN_MAX_FAILURES):
            _login(c, WRONG)
        _login(c, PASSWORD)                               # bloqueado (429)
    # tem de ter capturado algo, senão o teste não prova nada
    http = [r for r in app_logs.records if r.name == "steady.http"]
    assert len(http) >= 6
    fmt = JsonFormatter()
    everything = [fmt.format(r) + repr(r.__dict__) + repr(r.args) for r in app_logs.records]
    everything += [r.getMessage() + repr(r.__dict__) for r in caplog.records]
    blob = "\n".join(everything)
    for secret in (PASSWORD, WRONG, "x" * 50):
        assert secret not in blob
