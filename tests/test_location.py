from sqlalchemy import select
from models.location import Location
from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError, StatementError



# Test that locations can be created
def test_location_creation(db_session):
    # Test basic model creation
    location = Location(
        name_he="מיקום בדיקה",
        name_en="Test Location"
    )
    
    db_session.add(location)
    db_session.commit()
    
    assert location.id is not None
    assert location.name_he == "מיקום בדיקה"
    assert location.name_en == "Test Location"

# Test querying locations from database
def test_location_query(db_session):
    location = Location(
        name_he="מיקום בדיקה",
        name_en="Test Location"
    )
    
    db_session.add(location)
    db_session.commit()
    
    stmt = select(Location).where(Location.name_en == "Test Location")
    retrieved_location = db_session.execute(stmt).scalar_one_or_none()
    
    assert retrieved_location is not None
    assert retrieved_location.id == location.id
    assert retrieved_location.name_he == "מיקום בדיקה"
    assert retrieved_location.name_en == "Test Location"