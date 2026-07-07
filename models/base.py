import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

# Load independently of app.config to avoid a circular import (app/__init__.py
# imports models.base, and app.config lives inside the same `app` package).
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3")

engine = create_engine(DATABASE_URL)

class Base(DeclarativeBase):
    pass
