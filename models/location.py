from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import create_engine
from models.base import Base

engine = create_engine("sqlite:///db.sqlite3") # create the engine


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str] = mapped_column(String)
    name_en: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(nullable=False)
    lon: Mapped[float] = mapped_column(nullable=False)