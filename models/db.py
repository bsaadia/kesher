from sqlalchemy.orm import Session
from sqlalchemy import select
from models.base import Base, engine
from models.message import Message
from typing import List, Optional
from datetime import datetime

class MessageStorage():
    def __init__(self, session):
        self.session = session
    
    def add_message(self, telegram_id: int, timestamp: str, text: str, channel: str) -> Message:
        message = Message(telegram_id=telegram_id, timestamp=timestamp, text=text, channel=channel)
        self.session.add(message)
        self.session.commit()
        return message
    
    def get_all_messages(self) -> List[Message]:
        stmt = select(Message)
        return list(self.session.scalars(stmt))
    
    def get_message_within_timestamp_range(self, start: datetime, end: datetime) -> List[Message]:
        stmt = select(Message).where(
            Message.timestamp >= start,
            Message.timestamp <= end
        )
        return list(self.session.scalars(stmt))
    
    def delete_message(self, message: Message):
        self.session.delete(message)
        self.session.commit()
    
    def batch_add_messages(self, messages: List[Message]) -> List[Message]:
        self.session.add_all(messages)
        self.session.commit()
        return messages
        
    def close(self):
        self.session.close()