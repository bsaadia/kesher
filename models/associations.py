from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped
from models.base import Base

class MessageLocation(Base):
    __tablename__ = "message_locations"
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), primary_key=True)

    def to_dict(self):
        """Serializes the MessageLocation object to a dictionary."""
        return {
            "message_id": self.message_id,
            "location_id": self.location_id,
        }


class MessageActivity(Base):
    __tablename__ = "message_activities"
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)

    def to_dict(self):
        """Serializes the MessageActivity object to a dictionary."""
        return {
            "message_id": self.message_id,
            "activity_id": self.activity_id,
        }