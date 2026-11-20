import secrets
import hashlib
import time

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.entities import AuthSession, User


def require_admin(
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
