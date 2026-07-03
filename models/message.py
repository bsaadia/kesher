from datetime import datetime
from sqlalchemy import String, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import mapped_column, Mapped, relationship
from models.base import Base

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[str] = mapped_column(DateTime)
    text: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # A Telegram message id is unique within a channel; guard against re-inserting
    # the same message on incremental updates.
    __table_args__ = (
        UniqueConstraint("telegram_id", "channel", name="uq_message_telegram_channel"),
    )

    def to_dict(self):
        """Serializes the Message object to a dictionary."""
        return {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "channel": self.channel,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }
