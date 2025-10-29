from sqlalchemy import select
from models.location import Location
from models.associations import MessageLocation 
from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError, StatementError



# Test that MessageLocation associations can be created
def test_add_message_location_association(db_session, message_factory, location_factory):
    # Create a message and a location
    message = message_factory()
    location = location_factory()

    # Create the association
    association = MessageLocation(message_id=message.id, location_id=location.id)
    db_session.add(association)
    db_session.commit()

    # Query the association back
    stmt = select(MessageLocation).where(
        MessageLocation.message_id == message.id,
        MessageLocation.location_id == location.id
    )
    retrieved_association = db_session.execute(stmt).scalar_one_or_none()

    assert retrieved_association is not None
    assert retrieved_association.message_id == message.id

# Test that multiple locations can be associated with a single message
def test_multiple_locations_per_message(db_session, message_factory, location_factory):
    message = message_factory()
    location1 = location_factory(name_en="Location 1", name_he="מיקום 1")
    location2 = location_factory(name_en="Location 2", name_he="מיקום 2")
    association1 = MessageLocation(message_id=message.id, location_id=location1.id)
    association2 = MessageLocation(message_id=message.id, location_id=location2.id)
    db_session.add_all([association1, association2])
    db_session.commit()
    stmt = select(MessageLocation).where(MessageLocation.message_id == message.id)
    results = db_session.execute(stmt).scalars().all()
    assert len(results) == 2