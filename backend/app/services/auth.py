import base64
import functools
import hashlib
import hmac
import ipaddress
import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AccountLoginAttempt, AuditLog, AuthSession, LoginAttempt, User

SESSION_TTL_SECONDS = 12 * 60 * 60
SESSION_COOKIE = "steady_session"

# --- senha --------------------------------------------------------------------------------------
# Limite máximo de tamanho (caracteres). Acima disso a senha é RECUSADA (nunca truncada): evita que
# uma senha enorme consuma CPU/memória no hash. O mínimo de 12 vale só ao CRIAR a conta proprietária.
MAX_PASSWORD_LENGTH = 128
# Parâmetros Argon2id (perfil de baixa memória do RFC 9106). Mudar qualquer um deles faz os hashes
# existentes serem regravados no próximo login bem-sucedido (check_needs_rehash).
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KIB = 64 * 1024
ARGON2_PARALLELISM = 4
_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST, memory_cost=ARGON2_MEMORY_COST_KIB, parallelism=ARGON2_PARALLELISM
)
# No máximo N verificações de senha ao mesmo tempo: cada uma usa ~64 MiB, então sem isso um surto de
# logins simultâneos poderia esgotar a memória.
_HASH_SLOTS = threading.BoundedSemaphore(4)


def hash_password(password: str) -> str:
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve ter no máximo {MAX_PASSWORD_LENGTH} caracteres")
    return _hasher.hash(password)


def _verify_legacy_pbkdf2(password: str, password_hash: str) -> bool:
    """Formato antigo do PR nº 1 (pbkdf2_sha256$rounds$salt$digest). Só verifica; nunca é gerado de novo."""
    try:
        algorithm, rounds, salt, expected = password_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def verify_password(password: str, password_hash: str) -> bool:
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    if password_hash.startswith("$argon2"):
        try:
            return _hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False
    return _verify_legacy_pbkdf2(password, password_hash)


def password_needs_rehash(password_hash: str) -> bool:
    """True para hashes legados (PBKDF2), formatos desconhecidos ou Argon2 com parâmetros desatualizados."""
    if not password_hash.startswith("$argon2"):
        return True
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@functools.cache
def _dummy_hash() -> str:
    """Hash descartável (mesmo algoritmo e parâmetros) para gastar o mesmo tempo com e-mail inexistente."""
    return _hasher.hash("senha-descartavel-sem-uso")


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
    if len(settings.owner_password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"OWNER_PASSWORD deve ter no máximo {MAX_PASSWORD_LENGTH} caracteres")
    existing = db.scalar(select(User).where(User.email == settings.owner_email))
    if existing is None:
        db.add(User(email=settings.owner_email, password_hash=hash_password(settings.owner_password)))
        db.commit()


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


def audit_auth(db: Session, action: str, ip: str, *, email: str | None = None, **detail) -> None:
    """Auditoria de autenticação. NUNCA recebe a senha. Em falhas o e-mail digitado não é gravado
    (pode ser uma senha digitada no campo errado); só o IP em hash e se a conta existe."""
    db.add(AuditLog(actor=email or "anonymous", action=action, detail={"ip_hash": _ip_hash(ip)[:16], **detail}))
    db.commit()


# --- IP do cliente ------------------------------------------------------------------------------
@functools.lru_cache(maxsize=8)
def _trusted_networks(raw: tuple[str, ...]):
    return tuple(ipaddress.ip_network(item, strict=False) for item in raw)


def _parse_ip(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """IP do cliente. X-Forwarded-For só é lido quando quem se conectou é um proxy configurado em
    TRUSTED_PROXIES; nesse caso percorre a lista da direita para a esquerda e devolve o primeiro endereço
    que NÃO é de um proxy confiável (valores anteriores são controlados pelo cliente e ignorados)."""
    peer = request.client.host if request.client else "unknown"
    trusted = _trusted_networks(get_settings().trusted_proxies)
    peer_ip = _parse_ip(peer)
    if not trusted or peer_ip is None or not any(peer_ip in net for net in trusted):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    for part in reversed([p for p in forwarded.split(",") if p.strip()]):
        candidate = _parse_ip(part)
        if candidate is None:
            return peer  # cabeçalho malformado: não confia em nada dele
        if not any(candidate in net for net in trusted):
            return str(candidate)
    return peer


# --- limite de tentativas -----------------------------------------------------------------------
# Por CONTA: depois de LOGIN_MAX_FAILURES tentativas a conta é bloqueada temporariamente, com atraso
# progressivo (30 s, 60 s, 120 s ... até 15 min). Vale de qualquer IP, então espalhar o ataque por vários
# IPs não ajuda. Nunca é permanente: o bloqueio expira sozinho.
# Por IP: limite maior (IP_MAX_FAILURES por janela), para frear um único IP que testa várias contas sem
# que um IP compartilhado derrube o proprietário por muito tempo (bloqueio de no máximo uma janela).
# As tentativas são CONTADAS ANTES de verificar a senha, com atualização atômica (compare-and-swap), para
# que requisições simultâneas não passem do limite.
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5          # tentativas por conta antes do primeiro bloqueio
IP_MAX_FAILURES = 20            # falhas por IP dentro de LOGIN_WINDOW_SECONDS
ACCOUNT_LOCK_BASE_SECONDS = 30
ACCOUNT_LOCK_MAX_SECONDS = 15 * 60
ACCOUNT_RESET_SECONDS = 60 * 60  # sem tentativas por este tempo, o contador da conta zera
_CAS_RETRIES = 12


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        429,
        "Muitas tentativas de login. Tente novamente mais tarde.",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _account_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _cas_apply(db: Session, model, key_attr: str, key: str, now: int, decide) -> int | None:
    """Lê o estado, calcula o novo com `decide(state, now)` e grava só se ninguém mudou a linha no meio
    (compare-and-swap). `decide` devolve (novo_estado, retry_after): retry_after != None recusa a tentativa.
    Devolve retry_after (recusada) ou None (tentativa registrada). Se não conseguir gravar, falha FECHADO."""
    column = getattr(model, key_attr)
    for _ in range(_CAS_RETRIES):
        try:
            row = db.execute(
                select(model.failures, model.window_started_at, model.blocked_until).where(column == key)
            ).first()
            state = tuple(row) if row else None
            new_state, retry_after = decide(state, now)
            if new_state is None:  # já estava bloqueado: nada a gravar
                db.rollback()
                return retry_after
            failures, window_started_at, blocked_until = new_state
            if state is None:
                db.add(model(**{key_attr: key}, failures=failures, window_started_at=window_started_at,
                              blocked_until=blocked_until))
                db.commit()
                return retry_after
            result = db.execute(
                update(model)
                .where(
                    column == key,
                    model.failures == state[0],
                    model.window_started_at == state[1],
                    model.blocked_until.is_(None) if state[2] is None else model.blocked_until == state[2],
                )
                .values(failures=failures, window_started_at=window_started_at, blocked_until=blocked_until)
            )
            db.commit()
            if result.rowcount == 1:
                return retry_after
        except (IntegrityError, OperationalError):
            db.rollback()  # outra requisição gravou primeiro (ou o SQLite estava ocupado): tenta de novo
        time.sleep(0.005)
    return LOGIN_WINDOW_SECONDS


def _decide_ip(state, now: int):
    if state is None:
        return (1, now, None), None
    failures, window_started_at, blocked_until = state
    if blocked_until and blocked_until > now:
        return None, blocked_until - now
    if now - window_started_at >= LOGIN_WINDOW_SECONDS:
        return (1, now, None), None
    failures += 1
    if failures > IP_MAX_FAILURES:
        until = window_started_at + LOGIN_WINDOW_SECONDS
        return (failures, window_started_at, until), max(1, until - now)
    return (failures, window_started_at, None), None


def _account_lock_delay(attempts: int) -> int | None:
    if attempts < LOGIN_MAX_FAILURES:
        return None
    return min(ACCOUNT_LOCK_BASE_SECONDS * 2 ** (attempts - LOGIN_MAX_FAILURES), ACCOUNT_LOCK_MAX_SECONDS)


def _decide_account(state, now: int):
    if state is None:
        attempts, blocked_until = 1, None
    else:
        failures, last_attempt, blocked_until = state
        if blocked_until and blocked_until > now:
            return None, blocked_until - now
        attempts = 1 if now - last_attempt >= ACCOUNT_RESET_SECONDS else failures + 1
    delay = _account_lock_delay(attempts)
    return (attempts, now, now + delay if delay else None), None


def _refund_ip(db: Session, ip: str) -> None:
    """Devolve a tentativa reservada do IP (login correto, ou tentativa barrada pela conta)."""
    db.execute(
        update(LoginAttempt)
        .where(LoginAttempt.ip_hash == _ip_hash(ip), LoginAttempt.failures > 0)
        .values(failures=LoginAttempt.failures - 1)
    )
    db.commit()


def _clear_account_failures(db: Session, email: str) -> None:
    attempt = db.get(AccountLoginAttempt, _account_hash(email))
    if attempt:
        db.delete(attempt)
        db.commit()


def reserve_login_attempt(db: Session, ip: str, email: str, now: int) -> None:
    """Reserva uma tentativa para o IP e para a conta ANTES de verificar a senha; levanta 429 se barrada."""
    retry = _cas_apply(db, LoginAttempt, "ip_hash", _ip_hash(ip), now, _decide_ip)
    if retry is not None:
        audit_auth(db, "auth.login_blocked", ip, scope="ip")
        raise _too_many(retry)
    retry = _cas_apply(db, AccountLoginAttempt, "account_hash", _account_hash(email), now, _decide_account)
    if retry is not None:
        _refund_ip(db, ip)
        audit_auth(db, "auth.login_blocked", ip, scope="account")
        raise _too_many(retry)


def authenticate(db: Session, email: str, password: str, ip: str) -> tuple[User, str]:
    now = int(time.time())
    normalized_email = email.strip().lower()
    reserve_login_attempt(db, ip, normalized_email, now)
    user = db.scalar(select(User).where(User.email == normalized_email))
    with _HASH_SLOTS:
        password_valid = verify_password(password, user.password_hash if user else _dummy_hash())
    valid = user is not None and password_valid
    if not valid or not user.is_active:
        audit_auth(db, "auth.login_failed", ip, known_user=user is not None)
        raise HTTPException(401, "E-mail ou senha inválidos")
    _refund_ip(db, ip)
    _clear_account_failures(db, normalized_email)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)  # migração: PBKDF2 antigo ou parâmetros Argon2 novos
        db.commit()
    raw_token = secrets.token_urlsafe(32)
    db.add(AuthSession(
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        user_id=user.id,
        expires_at=now + SESSION_TTL_SECONDS,
    ))
    db.commit()
    audit_auth(db, "auth.login_success", ip, email=user.email)
    return user, raw_token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=get_settings().auth_cookie_secure,
                           samesite="strict")
