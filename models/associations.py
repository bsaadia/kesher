from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import create_engine
from models.base import Base

engine = create_engine("sqlite:///db.sqlite3") # create the engine

class MessageLocation(Base):
    __tablename__ = "message_locations"
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), primary_key=True)