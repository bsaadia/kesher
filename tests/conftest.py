import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models.message import Base

@pytest.fixture
def db_session():
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session
    
    session.close()
