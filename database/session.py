from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from config.settings import AppSettings
from database.base import Base


SessionFactory = Callable[[], Session]


def create_engine_from_settings(settings: AppSettings) -> Engine:
    if settings.database.url.startswith("sqlite:///"):
        settings.database.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            settings.database.url,
            connect_args={"check_same_thread": False},
            future=True,
        )
    return create_engine(settings.database.url, future=True)


def create_session_factory(settings: AppSettings) -> sessionmaker[Session]:
    engine = create_engine_from_settings(settings)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def initialize_database(settings: AppSettings) -> None:
    import database.models  # noqa: F401

    session_factory = create_session_factory(settings)
    engine = session_factory.kw["bind"]
    if not isinstance(engine, Engine):
        raise RuntimeError("Unable to initialize database engine.")
    Base.metadata.create_all(engine)


def sqlite_url_from_path(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"
