import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AuthSession, LoginAttempt, User

PASSWORD_HASH_ROUNDS = 260_000
SESSION_TTL_SECONDS = 12 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5
SESSION_COOKIE = "steady_session"
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$"
    "AAAAAAAAAAAAAAAAAAAAAA$"
    "9q6We4VltjMxPBmSgkDkFjl8f8NzRx6jvD3ktm+Vq9o"
)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_HASH_ROUNDS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_HASH_ROUNDS,
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, rounds, salt, expected = password_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), _b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(actual, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def ensure_owner_account(db: Session) -> None:
    settings = get_settings()
    if not settings.owner_email and not settings.owner_password:
        return
    if not settings.owner_email or not settings.owner_password:
        raise ValueError("Configure OWNER_EMAIL e OWNER_PASSWORD juntos")
    if "@" not in settings.owner_email or any(char.isspace() for char in settings.owner_email):
        raise ValueError("OWNER_EMAIL deve ser um endereço de e-mail válido")
    if len(settings.owner_password) < 12:
        raise ValueError("OWNER_PASSWORD deve ter pelo menos 12 caracteres")
    existing = db.scalar(select(User).where(User.email == settings.owner_email))
    if existing is None:
        db.add(User(email=settings.owner_email, password_hash=hash_password(settings.owner_password)))
        db.commit()


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


def ensure_login_allowed(db: Session, ip: str, now: int) -> None:
    attempt = db.get(LoginAttempt, _ip_hash(ip))
    if attempt and attempt.blocked_until and attempt.blocked_until > now:
        retry_after = attempt.blocked_until - now
        raise HTTPException(
            429,
            "Muitas tentativas de login. Tente novamente mais tarde.",
            headers={"Retry-After": str(retry_after)},
        )


def record_login_failure(db: Session, ip: str, now: int) -> None:
    ip_hash = _ip_hash(ip)
    attempt = db.get(LoginAttempt, ip_hash)
    if attempt is None:
        attempt = LoginAttempt(ip_hash=ip_hash, failures=0, window_started_at=now)
        db.add(attempt)
    elif now - attempt.window_started_at >= LOGIN_WINDOW_SECONDS:
        attempt.failures = 0
        attempt.window_started_at = now
        attempt.blocked_until = None
    attempt.failures += 1
    if attempt.failures >= LOGIN_MAX_FAILURES:
        attempt.blocked_until = now + LOGIN_WINDOW_SECONDS
    db.commit()


def clear_login_failures(db: Session, ip: str) -> None:
    attempt = db.get(LoginAttempt, _ip_hash(ip))
    if attempt:
        db.delete(attempt)
        db.commit()


def authenticate(db: Session, email: str, password: str, ip: str) -> tuple[User, str]:
    now = int(time.time())
    ensure_login_allowed(db, ip, now)
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    password_valid = verify_password(
        password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )
    valid = user is not None and password_valid
    if not valid or not user.is_active:
        record_login_failure(db, ip, now)
        raise HTTPException(401, "E-mail ou senha inválidos")
    clear_login_failures(db, ip)
    raw_token = secrets.token_urlsafe(32)
    db.add(AuthSession(
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        user_id=user.id,
        expires_at=now + SESSION_TTL_SECONDS,
    ))
    db.commit()
    return user, raw_token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=get_settings().auth_cookie_secure,
                           samesite="lax")
