from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped
from models.base import Base

class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String, unique=True)

    def to_dict(self):
        """Serializes the Activity object to a dictionary."""
        return {
            "id": self.id,
            "category": self.category,
        }
