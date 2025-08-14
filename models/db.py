from sqlalchemy.orm import Session
from sqlalchemy import select
from models.message import Base, Message, engine
from typing import List, Optional

# Create tables
Base.metadata.create_all(engine)

class MessageStorage:
    def __init__(self):
        self.session = Session(engine)
    
    def add_message(self, timestamp: str, text: str, channel: str) -> Message:
        message = Message(timestamp=timestamp, text=text, channel=channel)
        self.session.add(message)
        self.session.commit()
        return message
    
    def get_messages_by_channel(self, channel: str) -> List[Message]:
        stmt = select(Message).where(Message.channel == channel)
        return list(self.session.scalars(stmt))
    
    def get_all_messages(self) -> List[Message]:
        stmt = select(Message)
        return list(self.session.scalars(stmt))
    
    def get_message_by_id(self, message_id: int) -> Optional[Message]:
        stmt = select(Message).where(Message.id == message_id)
        return self.session.scalar(stmt)
    
    def close(self):
        self.session.close()