import hashlib

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.database.session import get_db
from app.models.entities import AuthSession
from app.services.auth import (
    SESSION_COOKIE,
    authenticate,
    clear_session_cookie,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    _, token = authenticate(db, body.email, body.password, request.client.host if request.client else "unknown")
    set_session_cookie(response, token)
    return {"ok": True}


@router.get("/me")
def current_user(email: str = Depends(require_admin)):
    return {"email": email}


@router.post("/logout")
def logout(
    response: Response,
    steady_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
):
    if steady_session:
        token_hash = hashlib.sha256(steady_session.encode()).hexdigest()
        session = db.get(AuthSession, token_hash)
        if session:
            db.delete(session)
            db.commit()
    clear_session_cookie(response)
    return {"ok": True}
