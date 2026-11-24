import hashlib

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import check_origin, csrf_token_for, require_admin, verify_csrf
from app.database.session import get_db
from app.models.entities import AuthSession, User
from app.services.auth import (
    SESSION_COOKIE,
    MAX_PASSWORD_LENGTH,
    audit_auth,
    authenticate,
    clear_session_cookie,
    client_ip,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)  # recusa, nunca trunca


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)  # barra login CSRF vindo de outro site
    _, token = authenticate(db, body.email, body.password, client_ip(request))
    set_session_cookie(response, token)
    return {"ok": True, "csrf_token": csrf_token_for(token)}


@router.get("/me")
def current_user(email: str = Depends(require_admin)):
    return {"email": email}


@router.get("/csrf")
def csrf(email: str = Depends(require_admin), steady_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    """Devolve o token CSRF da sessão atual (o painel o envia no cabeçalho X-CSRF-Token)."""
    if not steady_session:
        raise HTTPException(400, "Token CSRF só existe para sessões por cookie")
    return {"csrf_token": csrf_token_for(steady_session)}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    steady_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
):
    if steady_session:
        verify_csrf(request, steady_session)
        token_hash = hashlib.sha256(steady_session.encode()).hexdigest()
        session = db.get(AuthSession, token_hash)
        if session:
            user = db.get(User, session.user_id)
            db.delete(session)
            db.commit()
            audit_auth(db, "auth.logout", client_ip(request),
                       email=user.email if user else None)
    clear_session_cookie(response)
    return {"ok": True}
