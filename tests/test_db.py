from sqlalchemy import select
from models.message import Message
from models.db import MessageStorage
from datetime import datetime

# test that messages can be created
def test_add_message(db_session):
    storage = MessageStorage(db_session)
    
    timestamp = datetime.now()
    text = "test message"
    channel = "test channel"

    added_message = storage.add_message(timestamp=timestamp, text=text, channel=channel)

    # check is message was added correctly
    assert added_message.text == text
    assert added_message.channel == channel

    # query database directly to ensure the data was persisted
    stmt = select(Message).where(Message.text == text)
    retrieved_message = db_session.execute(stmt).scalar_one_or_none()
    assert retrieved_message is not None
    assert retrieved_message.text == text
    assert retrieved_message.channel == channel
    assert retrieved_message.timestamp is not None

    # both should be the same instance
    assert added_message.id == retrieved_message.id

# test that messages can be deleted
def test_delete_message(db_session):
    storage = MessageStorage(db_session)
    
    timestamp = datetime.now()
    text = "message to be deleted"
    channel = "test channel"

    added_message = storage.add_message(timestamp=timestamp, text=text, channel=channel)

    # delete the message
    storage.delete_message(added_message)

    # check that the message was deleted
    stmt = select(Message).where(Message.text == text)
    retrieved_message = db_session.execute(stmt).scalar_one_or_none()
    assert retrieved_message is None

# test getting all messages
def test_get_all_messages(db_session):
    storage = MessageStorage(db_session)
    
    timestamp = datetime.now()
    text = "message for retrieval"
    channel = "test channel"

    added_message = storage.add_message(timestamp=timestamp, text=text, channel=channel)

    # retrieve all messages
    all_messages = storage.get_all_messages()

    # check if the added message is in the retrieved list
    assert len(all_messages) > 0
    assert added_message in all_messages

    # verify the retrieved message matches the added message
    retrieved_message = next((msg for msg in all_messages if msg.id == added_message.id), None)
    assert retrieved_message is not None
    assert retrieved_message.text == text
    assert retrieved_message.channel == channel

# test getting messages within a timestamp range
def test_get_messages_within_timestamp_range(db_session):
    storage = MessageStorage(db_session)
    
    start_time = datetime.now()
    text1 = "message within range 1"
    text2 = "message within range 2"
    channel = "test channel"

    # Add two messages
    storage.add_message(timestamp=start_time, text=text1, channel=channel)
    storage.add_message(timestamp=start_time, text=text2, channel=channel)

    # Define a time range that includes both messages
    end_time = datetime.now()

    # Retrieve messages within the timestamp range
    messages_in_range = storage.get_message_within_timestamp_range(start=start_time, end=end_time)

    assert len(messages_in_range) == 2
    assert all(msg.text in [text1, text2] for msg in messages_in_range)