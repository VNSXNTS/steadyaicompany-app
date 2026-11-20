import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_url = _settings.database_url
_connect_args = {}
if _url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    path = _url.replace("sqlite:///", "", 1)
    if path and path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

engine = create_engine(_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
