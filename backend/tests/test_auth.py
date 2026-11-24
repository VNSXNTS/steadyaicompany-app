import time

from fastapi.testclient import TestClient

from app.main import app
from app.models.entities import AccountLoginAttempt, AuthSession, LoginAttempt, User
from app.services.auth import ACCOUNT_RESET_SECONDS, LOGIN_WINDOW_SECONDS, hash_password, verify_password


def test_password_hash_is_salted_and_verified():
    first = hash_password("strong-password")
    second = hash_password("strong-password")
    assert first != second
    assert verify_password("strong-password", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("strong-password", "invalid")


def test_login_session_and_logout(db):
    with TestClient(app) as anon:
        login = anon.post("/auth/login", json={"email": "OWNER@example.com", "password": "test-password"})
        assert login.status_code == 200
        anon.headers["X-CSRF-Token"] = login.json()["csrf_token"]  # logout altera estado: exige CSRF
        assert "httponly" in login.headers["set-cookie"].lower()
        assert anon.get("/auth/me").json() == {"email": "owner@example.com"}
        assert anon.get("/agents").status_code == 200

        session = db.query(AuthSession).one()
        session.expires_at = int(time.time()) - 1
        db.commit()
        assert anon.get("/auth/me").status_code == 401
        assert anon.post("/auth/logout").json() == {"ok": True}
        assert anon.get("/auth/me").status_code == 401
    assert db.query(AuthSession).count() == 0
    owner = db.query(User).one()
    assert owner.password_hash != "test-password"


def test_login_rate_limit_blocks_after_five_failures(db):
    with TestClient(app) as anon:
        for _ in range(5):
            response = anon.post("/auth/login", json={"email": "owner@example.com", "password": "wrong"})
            assert response.status_code == 401
        blocked = anon.post("/auth/login", json={"email": "owner@example.com", "password": "wrong"})
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        attempt = db.query(LoginAttempt).one()
        attempt.window_started_at = int(time.time()) - LOGIN_WINDOW_SECONDS
        attempt.blocked_until = int(time.time()) - 1
        account = db.query(AccountLoginAttempt).one()  # o bloqueio agora é por conta (e por IP)
        account.window_started_at = int(time.time()) - ACCOUNT_RESET_SECONDS
        account.blocked_until = int(time.time()) - 1
        db.commit()
        assert anon.post("/auth/login", json={"email": "owner@example.com", "password": "wrong"}).status_code == 401
