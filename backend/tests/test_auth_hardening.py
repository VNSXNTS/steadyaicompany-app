"""Testes das correções do PR nº 1: Argon2id e migração de hash (M3), limite de senha (B5), bloqueio por
conta/IP e concorrência (M1), Secure em produção (M2), /docs (B1) e CSRF (B2)."""
import dataclasses
import hashlib
import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import get_settings
from app.main import app, create_app
from app.models.entities import AccountLoginAttempt, AuthSession, LoginAttempt, User
from app.services import auth as auth_service
from app.services.auth import (
    ACCOUNT_RESET_SECONDS, IP_MAX_FAILURES, LOGIN_MAX_FAILURES, LOGIN_WINDOW_SECONDS, MAX_PASSWORD_LENGTH,
    SESSION_COOKIE, client_ip, hash_password, password_needs_rehash, verify_password,
)

OWNER = "owner@example.com"
PASSWORD = "test-password"
WRONG = "wrong-password-xyz-123"


def _login(c, password=PASSWORD, email=OWNER, **kw):
    return c.post("/auth/login", json={"email": email, "password": password}, **kw)


def _legacy_pbkdf2(password: str, rounds: int = 260_000) -> str:
    salt = b"0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return f"pbkdf2_sha256${rounds}${enc(salt)}${enc(digest)}"


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


# ------------------------------------------------------------------ M3: Argon2id e migração
def test_new_hashes_are_argon2id_and_salted():
    a, b = hash_password("senha-forte-123"), hash_password("senha-forte-123")
    assert a.startswith("$argon2id$") and a != b
    assert verify_password("senha-forte-123", a) and not verify_password("outra", a)
    assert not verify_password("x", "lixo") and not verify_password("x", "$argon2id$quebrado")
    assert not password_needs_rehash(a)


def test_legacy_pbkdf2_hash_still_verifies_and_is_flagged_for_rehash():
    legacy = _legacy_pbkdf2("senha-antiga-123")
    assert verify_password("senha-antiga-123", legacy) and not verify_password("errada", legacy)
    assert password_needs_rehash(legacy)


def test_legacy_hash_is_migrated_to_argon2id_on_next_login(db):
    with TestClient(app):
        pass
    user = db.query(User).one()
    user.password_hash = _legacy_pbkdf2(PASSWORD)
    db.commit()
    with TestClient(app) as c:
        assert _login(c, WRONG).status_code == 401
        db.expire_all()
        assert db.query(User).one().password_hash.startswith("pbkdf2_sha256$")  # falha não migra
        assert _login(c).status_code == 200
    db.expire_all()
    migrated = db.query(User).one().password_hash
    assert migrated.startswith("$argon2id$") and PASSWORD not in migrated
    with TestClient(app) as c:
        assert _login(c).status_code == 200  # continua entrando com o hash novo


def test_hash_with_outdated_argon2_parameters_is_rehashed_on_login(db):
    with TestClient(app):
        pass
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    assert password_needs_rehash(weak) and verify_password(PASSWORD, weak)
    user = db.query(User).one()
    user.password_hash = weak
    db.commit()
    with TestClient(app) as c:
        assert _login(c).status_code == 200
    db.expire_all()
    new = db.query(User).one().password_hash
    assert new != weak and not password_needs_rehash(new)


# ------------------------------------------------------------------ B5: tamanho da senha
def test_password_longer_than_limit_is_rejected_never_truncated(db):
    exact = "A" * MAX_PASSWORD_LENGTH
    with TestClient(app) as c:
        user = db.query(User).one()
        user.password_hash = hash_password(exact)
        db.commit()
        assert _login(c, exact).status_code == 200
        too_long = _login(c, exact + "B")  # se fosse truncada, entraria
        assert too_long.status_code == 422
        assert SESSION_COOKIE not in too_long.headers.get("set-cookie", "")
        assert _login(c, "x" * 100_000).status_code == 422
    assert not verify_password(exact + "B", hash_password(exact))
    with pytest.raises(ValueError):
        hash_password("A" * (MAX_PASSWORD_LENGTH + 1))


def test_owner_bootstrap_rejects_too_long_password(monkeypatch, db):
    monkeypatch.setenv("OWNER_EMAIL", "novo@example.com")
    monkeypatch.setenv("OWNER_PASSWORD", "A" * (MAX_PASSWORD_LENGTH + 1))
    with pytest.raises(ValueError, match="no máximo"):
        auth_service.ensure_owner_account(db)


# ------------------------------------------------------------------ M1: bloqueio por conta e IP
@pytest.fixture()
def rotating_ips(monkeypatch):
    counter = iter(range(1, 10_000))
    monkeypatch.setattr("app.api.auth.client_ip", lambda request: f"203.0.113.{next(counter) % 250}-{next(counter)}")


def test_account_lock_holds_across_many_ips(rotating_ips):
    with TestClient(app) as c:
        for _ in range(LOGIN_MAX_FAILURES):
            assert _login(c, WRONG).status_code == 401  # cada tentativa chega de um IP diferente
        blocked = _login(c, PASSWORD)  # senha certa, IP novo, mas a CONTA está bloqueada
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_unknown_email_is_throttled_like_a_known_one():
    with TestClient(app) as c:
        for _ in range(LOGIN_MAX_FAILURES):
            assert _login(c, WRONG, email="ninguem@example.com").status_code == 401
        assert _login(c, WRONG, email="ninguem@example.com").status_code == 429


def test_account_lock_is_temporary_and_progressive(db):
    with TestClient(app) as c:
        for _ in range(LOGIN_MAX_FAILURES):
            _login(c, WRONG)
        acct = db.query(AccountLoginAttempt).one()
        first = acct.blocked_until - int(time.time())
        assert 0 < first <= auth_service.ACCOUNT_LOCK_BASE_SECONDS
        acct.blocked_until = int(time.time()) - 1  # o bloqueio expira sozinho
        db.commit()
        assert _login(c, WRONG).status_code == 401  # voltou a poder tentar
        db.expire_all()
        second = db.query(AccountLoginAttempt).one().blocked_until - int(time.time())
        assert second > first  # atraso dobrou
        acct = db.query(AccountLoginAttempt).one()
        acct.blocked_until = int(time.time()) - 1
        db.commit()
        assert _login(c).status_code == 200  # senha certa depois do bloqueio: entra
        assert db.query(AccountLoginAttempt).count() == 0  # sucesso zera a conta


def test_account_lock_never_exceeds_cap(db):
    with TestClient(app) as c:
        for _ in range(LOGIN_MAX_FAILURES):
            _login(c, WRONG)
        acct = db.query(AccountLoginAttempt).one()
        acct.failures = 500
        acct.blocked_until = None
        db.commit()
        _login(c, WRONG)
        db.expire_all()
        assert db.query(AccountLoginAttempt).one().blocked_until - int(time.time()) <= auth_service.ACCOUNT_LOCK_MAX_SECONDS


def test_account_counter_resets_after_idle_period(db):
    with TestClient(app) as c:
        for _ in range(LOGIN_MAX_FAILURES - 1):
            _login(c, WRONG)
        acct = db.query(AccountLoginAttempt).one()
        acct.window_started_at = int(time.time()) - ACCOUNT_RESET_SECONDS
        db.commit()
        assert _login(c, WRONG).status_code == 401
        db.expire_all()
        assert db.query(AccountLoginAttempt).one().failures == 1


def test_shared_ip_with_other_accounts_does_not_lock_the_owner():
    with TestClient(app) as c:
        for i in range(IP_MAX_FAILURES - 1):  # vizinhos do mesmo IP errando (cada um uma conta)
            assert _login(c, WRONG, email=f"vizinho{i}@example.com").status_code == 401
        assert _login(c).status_code == 200  # o proprietário ainda entra


def test_ip_limit_is_temporary(db):
    with TestClient(app) as c:
        codes = [_login(c, WRONG, email=f"alvo{i}@example.com").status_code for i in range(IP_MAX_FAILURES + 3)]
        assert codes[:IP_MAX_FAILURES] == [401] * IP_MAX_FAILURES and set(codes[IP_MAX_FAILURES:]) == {429}
        blocked = _login(c)
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) <= LOGIN_WINDOW_SECONDS
        row = db.query(LoginAttempt).one()
        row.window_started_at = int(time.time()) - LOGIN_WINDOW_SECONDS
        row.blocked_until = int(time.time()) - 1
        db.commit()
        assert _login(c).status_code == 200  # não é permanente


def test_spoofed_forwarded_for_does_not_evade_ip_limit(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    with TestClient(app) as c:
        codes = [
            _login(c, WRONG, email=f"alvo{i}@example.com", headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code
            for i in range(IP_MAX_FAILURES + 2)
        ]
    assert codes[-1] == 429  # o cabeçalho forjado não criou IPs novos


def test_concurrent_attempts_cannot_exceed_account_limit(db):
    with TestClient(app):
        pass
    barrier = threading.Barrier(24)

    def attempt(_):
        client = TestClient(app)
        barrier.wait()
        return _login(client, WRONG).status_code

    with ThreadPoolExecutor(24) as pool:
        codes = list(pool.map(attempt, range(24)))
    assert codes.count(401) == LOGIN_MAX_FAILURES, codes  # exatamente o limite, nunca mais
    assert codes.count(429) == 24 - LOGIN_MAX_FAILURES


def test_concurrent_attempts_cannot_exceed_ip_limit():
    with TestClient(app):
        pass
    n = IP_MAX_FAILURES + 15
    barrier = threading.Barrier(n)

    def attempt(i):
        client = TestClient(app)
        barrier.wait()
        return _login(client, WRONG, email=f"conta{i}@example.com").status_code

    with ThreadPoolExecutor(n) as pool:
        codes = list(pool.map(attempt, range(n)))
    assert codes.count(401) == IP_MAX_FAILURES, codes


# ------------------------------------------------------------------ proxy confiável
def test_forwarded_for_ignored_without_trusted_proxy(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    assert client_ip(_request("10.0.0.5", "1.2.3.4")) == "10.0.0.5"


def test_forwarded_for_used_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/24, 172.16.0.9")
    assert client_ip(_request("10.0.0.5", "9.9.9.9")) == "9.9.9.9"
    assert client_ip(_request("10.0.0.5", "6.6.6.6, 9.9.9.9, 10.0.0.7")) == "9.9.9.9"  # ignora o que o cliente forjou
    assert client_ip(_request("8.8.8.8", "1.2.3.4")) == "8.8.8.8"  # quem conectou não é proxy confiável
    assert client_ip(_request("10.0.0.5")) == "10.0.0.5"  # sem cabeçalho
    assert client_ip(_request("10.0.0.5", "nao-e-ip")) == "10.0.0.5"  # malformado
    assert client_ip(_request("10.0.0.5", "10.0.0.6")) == "10.0.0.5"  # só proxies na lista


def test_invalid_trusted_proxies_is_rejected(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.1, banana")
    with pytest.raises(ValueError, match="TRUSTED_PROXIES"):
        get_settings()


# ------------------------------------------------------------------ M2: produção
def _prod(**kw):
    return dataclasses.replace(get_settings(), app_env="production", **kw)


def test_production_without_secure_cookie_refuses_to_start():
    with pytest.raises(RuntimeError, match="AUTH_COOKIE_SECURE=true"):
        create_app(_prod(auth_cookie_secure=False))


def test_production_via_environment_refuses_to_start(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        create_app()


def test_unknown_app_env_is_refused():
    with pytest.raises(RuntimeError, match="não é reconhecido"):
        create_app(dataclasses.replace(get_settings(), app_env="prod"))


def test_development_over_http_still_works():
    create_app(dataclasses.replace(get_settings(), app_env="development", auth_cookie_secure=False))
    with TestClient(app) as c:
        assert "secure" not in _login(c).headers["set-cookie"].lower().split("; ")


def test_production_with_secure_cookie_starts_and_sets_secure_flag(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    prod = create_app()
    with TestClient(prod, base_url="https://testserver") as c:
        header = _login(c).headers["set-cookie"].lower()
        assert "secure" in [a.strip() for a in header.split(";")]
        assert c.get("/health").status_code == 200


# ------------------------------------------------------------------ B1: /docs
DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_available_in_development(path):
    with TestClient(app) as c:
        assert c.get(path).status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_disabled_in_production(path):
    prod = create_app(_prod(auth_cookie_secure=True))
    with TestClient(prod) as c:
        assert c.get(path).status_code == 404
        assert c.get(path, headers={"X-API-Key": "test-key"}).status_code == 404  # nem autenticado


# ------------------------------------------------------------------ B2: CSRF
@pytest.fixture()
def session_client(db):
    with TestClient(app) as c:
        token = _login(c).json()["csrf_token"]
        yield c, token


def test_csrf_valid_token_allows_state_change(session_client):
    c, token = session_client
    assert c.post("/agents/market_hunter/pause", headers={"X-CSRF-Token": token}).status_code == 200


def test_csrf_missing_token_is_forbidden(session_client):
    c, _ = session_client
    assert c.post("/agents/market_hunter/pause").status_code == 403
    assert c.post("/tasks", json={"agent_key": "market_hunter", "description": "x" * 10}).status_code == 403


def test_csrf_invalid_token_is_forbidden(session_client):
    c, token = session_client
    for bad in ("", "abc", token[:-1] + ("0" if token[-1] != "0" else "1"), token.upper()):
        assert c.post("/agents/market_hunter/pause", headers={"X-CSRF-Token": bad}).status_code == 403


def test_csrf_token_from_another_session_is_forbidden(db):
    with TestClient(app) as a, TestClient(app) as b:
        token_a = _login(a).json()["csrf_token"]
        _login(b)
        assert b.post("/agents/market_hunter/pause", headers={"X-CSRF-Token": token_a}).status_code == 403
        assert a.post("/agents/market_hunter/pause", headers={"X-CSRF-Token": token_a}).status_code == 200


def test_csrf_not_needed_for_reads(session_client):
    c, _ = session_client
    assert c.get("/agents").status_code == 200


def test_csrf_endpoint_returns_session_token(session_client):
    c, token = session_client
    assert c.get("/auth/csrf").json() == {"csrf_token": token}


def test_csrf_endpoint_requires_cookie_session(client):  # `client` usa X-API-Key
    assert client.get("/auth/csrf").status_code == 400
    with TestClient(app) as anon:
        assert anon.get("/auth/csrf").status_code == 401


def test_cross_site_origin_is_forbidden_even_with_valid_token(session_client):
    c, token = session_client
    h = {"X-CSRF-Token": token}
    assert c.post("/agents/market_hunter/pause", headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/agents/market_hunter/pause", headers={**h, "Origin": "null"}).status_code == 403
    assert c.post("/agents/market_hunter/pause", headers={**h, "Origin": "http://testserver"}).status_code == 200


def test_allowed_origins_setting(session_client, monkeypatch):
    c, token = session_client
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://painel.example.com/")
    ok = c.post("/agents/market_hunter/pause",
                headers={"X-CSRF-Token": token, "Origin": "https://painel.example.com"})
    assert ok.status_code == 200


def test_login_from_foreign_origin_is_forbidden(db):
    with TestClient(app) as c:
        r = _login(c, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403 and SESSION_COOKIE not in r.headers.get("set-cookie", "")
        assert _login(c, headers={"Origin": "http://testserver"}).status_code == 200


def test_logout_requires_csrf_and_keeps_session_when_missing(session_client, db):
    c, token = session_client
    assert c.post("/auth/logout").status_code == 403
    assert db.query(AuthSession).count() == 1
    assert c.post("/auth/logout", headers={"X-CSRF-Token": token}).status_code == 200
    assert db.query(AuthSession).count() == 0


def test_api_key_requests_do_not_need_csrf_and_cannot_use_it_improperly(client):
    assert client.post("/agents/market_hunter/pause").status_code == 200  # integração por chave (não usa cookie)
    with TestClient(app) as anon:
        assert anon.post("/agents/market_hunter/pause", headers={"X-API-Key": "chave-errada"}).status_code == 401
        assert anon.post("/agents/market_hunter/pause").status_code == 401
        anon.cookies.set(SESSION_COOKIE, "inventado")
        assert anon.post("/agents/market_hunter/pause", headers={"X-API-Key": "test-key"}).status_code == 401
