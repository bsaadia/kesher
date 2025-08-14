from sqlalchemy import select
from models.message import Message
from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError, StatementError



# Test that messages can be created
def test_message_creation(db_session):
    # Test basic model creation
    message = Message(
        timestamp=datetime.now(),
        text="Test message",
        channel="general"
    )
    
    db_session.add(message)
    db_session.commit()
    
    assert message.id is not None
    assert message.text == "Test message"
    assert message.channel == "general"

# Test querying messages from database
def test_message_query(db_session):
    message = Message(
        timestamp=datetime.now(),
        text="Test message",
        channel="general"
    )

    db_session.add(message)
    db_session.commit()
    
    stmt = select(Message).where(Message.text == "Test message")
    found = db_session.execute(stmt).scalar_one_or_none()
    # Verify the query found the record
    assert found is not None
    # Verify the found record has correct data
    assert found.channel == "general"

# Test that database rejects null values for required fields
def test_message_null(db_session):
    message = Message(
        timestamp=None,
        text=None,
        channel=None
    )

    db_session.add(message)
    
    # Expect IntegrityError when committing null values to NOT NULL columns
    with pytest.raises(IntegrityError):
        db_session.commit()

# Test data type validation
def test_message_datatypes(db_session):
    
    message = Message(
        timestamp="not a datetime object",
        text="Test message",
        channel="general"
    )

    db_session.add(message)

    # Expect StatementError when committing invalid datetime type
    with pytest.raises(StatementError):
        db_session.commit()

# Test filtering by timestamp
def test_message_filtering_by_time(db_session):
    message = Message(
        timestamp=datetime(2025, 8, 13),
        text="Test message",
        channel="general"
    )

    db_session.add(message)
    db_session.commit()

    stmt = select(Message).where(Message.timestamp < datetime.now())
    found = db_session.execute(stmt).scalar_one_or_none()

    assert found is not None
    assert found.text == "Test message"
    assert found.channel == "general"