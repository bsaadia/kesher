from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped
from typing import Optional
from models.base import Base

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str] = mapped_column(String)
    name_en: Mapped[str] = mapped_column(String)
    name_ar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    front: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lat: Mapped[float] = mapped_column(nullable=False)
    lon: Mapped[float] = mapped_column(nullable=False)

    def to_dict(self):
        """Serializes the Location object to a dictionary."""
        return {
            "id": self.id,
            "name_he": self.name_he,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "front": self.front,
            "lat": self.lat,
            "lon": self.lon,
        }