import secrets
import hashlib
import time

from urllib.parse import urlparse

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.entities import AuthSession, User


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
CSRF_HEADER = "X-CSRF-Token"


def csrf_token_for(session_token: str) -> str:
    """Token CSRF atrelado à sessão: derivado (SHA-256) do token do cookie HttpOnly. Um site atacante não
    lê o cookie nem este valor, e o valor não revela o token da sessão. Não há segredo extra a configurar."""
    return hashlib.sha256(("steady-csrf:" + session_token).encode()).hexdigest()


def check_origin(request: Request) -> None:
    """Se o navegador mandou Origin, ela precisa ser o próprio painel (mesmo host) ou estar em
    ALLOWED_ORIGINS. Defesa em profundidade: não depende só de SameSite."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = get_settings().allowed_origins
    if origin.rstrip("/") in allowed:
        return
    host = request.headers.get("host")
    if origin != "null" and host and urlparse(origin).netloc == host:
        return
    raise HTTPException(403, "Origem não permitida")


def verify_csrf(request: Request, session_token: str) -> None:
    check_origin(request)
    sent = request.headers.get(CSRF_HEADER)
    if not sent or not secrets.compare_digest(sent, csrf_token_for(session_token)):
        raise HTTPException(403, "Token CSRF ausente ou inválido")


def require_admin(
    request: Request,
    x_api_key: str | None = Header(default=None),
    steady_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> str:
    """Aceita sessão de usuário ou chave de integração legada; falha fechado sem credenciais."""
    if steady_session:
        token_hash = hashlib.sha256(steady_session.encode()).hexdigest()
        session = db.get(AuthSession, token_hash)
        if session and session.expires_at > int(time.time()):
            user = db.get(User, session.user_id)
            if user and user.is_active:
                if request.method not in SAFE_METHODS:
                    verify_csrf(request, steady_session)  # só vale para autenticação por cookie
                return user.email
        raise HTTPException(401, "Sessão inválida ou expirada")

    settings = get_settings()
    if settings.admin_api_key:
        if x_api_key and secrets.compare_digest(x_api_key, settings.admin_api_key):
            return "admin"
        raise HTTPException(401, "Chave de API inválida")
    if settings.owner_email and settings.owner_password:
        raise HTTPException(401, "Autenticação necessária")
    raise HTTPException(503, "Configure OWNER_EMAIL e OWNER_PASSWORD ou ADMIN_API_KEY")
