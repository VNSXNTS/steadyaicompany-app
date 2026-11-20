import secrets

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_admin(x_api_key: str | None = Header(default=None)) -> str:
    """Protege os endpoints. Sem ADMIN_API_KEY configurada, tudo é recusado (fail closed)."""
    expected = get_settings().admin_api_key
    if not expected:
        raise HTTPException(503, "ADMIN_API_KEY não configurada no servidor")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Chave de API inválida")
    return "admin"
