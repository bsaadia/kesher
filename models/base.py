import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

# Load independently of app.config to avoid a circular import (app/__init__.py
# imports models.base, and app.config lives inside the same `app` package).
load_dotenv()


def normalize_database_url(url: str) -> str:
    # Some managed Postgres providers hand out "postgres://" URLs, which
    # SQLAlchemy 1.4+ no longer recognizes as a dialect (raises NoSuchModuleError).
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def build_engine(url: str):
    # Without connect_timeout, a psycopg2 connect() can hang indefinitely if the
    # TCP handshake never completes (e.g. a stale route right after the machine
    # wakes from sleep) — that hung an hourly-update run for over an hour and
    # blocked every subsequent run behind its lock file.
    url = normalize_database_url(url)
    connect_args = {"connect_timeout": 10} if url.startswith("postgresql://") else {}
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, connect_args=connect_args)


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///db.sqlite3"))
engine = build_engine(DATABASE_URL)

class Base(DeclarativeBase):
    pass
