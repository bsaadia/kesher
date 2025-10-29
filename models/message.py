from sqlalchemy import String, DateTime
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import create_engine
from models.base import Base

engine = create_engine("sqlite:///db.sqlite3") # create the engine

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[str] = mapped_column(DateTime)
    text: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String)
