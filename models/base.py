import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

# Load independently of app.config to avoid a circular import (app/__init__.py
# imports models.base, and app.config lives inside the same `app` package).
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")
# Some managed Postgres providers hand out "postgres://" URLs, which
# SQLAlchemy 1.4+ no longer recognizes as a dialect (raises NoSuchModuleError).
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

class Base(DeclarativeBase):
    pass
