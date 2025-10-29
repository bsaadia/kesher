from sqlalchemy import select
from datetime import datetime
import pytest
from sqlalchemy.exc import IntegrityError, StatementError

# Test loading gazetteer data into the database
def test_load_gazetteer_to_db_if_empty(db_session):
    from app.processor.processing import load_gazetteer_to_db_if_empty
    from models.location import Location

    # Ensure the Location table is empty
    db_session.query(Location).delete()
    db_session.commit()

    # Load gazetteer data
    load_gazetteer_to_db_if_empty(db_session)

    # Verify that locations were added
    location_count = db_session.query(Location).count()
    assert location_count > 0