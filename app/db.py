"""Database engine, session factory and schema helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver glue
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    _ensure_fts()


def _ensure_fts() -> None:
    """Create an SQLite FTS5 index when available; search falls back to LIKE."""
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        try:
            conn.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS listing_fts USING fts5("
                    "title, company, description_text, category, city, "
                    "content='listing', content_rowid='id')"
                )
            )
            conn.execute(
                text(
                    "CREATE TRIGGER IF NOT EXISTS listing_ai AFTER INSERT ON listing BEGIN "
                    "INSERT INTO listing_fts(rowid,title,company,description_text,category,city) "
                    "VALUES (new.id,new.title,new.company,new.description_text,new.category,new.city); END"
                )
            )
            conn.execute(
                text(
                    "CREATE TRIGGER IF NOT EXISTS listing_ad AFTER DELETE ON listing BEGIN "
                    "INSERT INTO listing_fts(listing_fts,rowid,title,company,description_text,category,city) "
                    "VALUES('delete',old.id,old.title,old.company,old.description_text,old.category,old.city); END"
                )
            )
            conn.execute(
                text(
                    "CREATE TRIGGER IF NOT EXISTS listing_au AFTER UPDATE ON listing BEGIN "
                    "INSERT INTO listing_fts(listing_fts,rowid,title,company,description_text,category,city) "
                    "VALUES('delete',old.id,old.title,old.company,old.description_text,old.category,old.city); "
                    "INSERT INTO listing_fts(rowid,title,company,description_text,category,city) "
                    "VALUES (new.id,new.title,new.company,new.description_text,new.category,new.city); END"
                )
            )
        except Exception:
            # FTS5 is optional. The search layer transparently falls back to LIKE.
            pass
