from datetime import datetime
import pandas as pd
import os
from models.location import Location

GAZETTEER_PATH = os.path.join("scrap", "gaza_gazetteer.csv")

def load_gazetteer_to_db_if_empty(db_session):
    """
    Loads gazetteer data into the database if the Location table is empty.
    Args:
        db_session: SQLAlchemy session object
    Returns:
        None
    """

    # Check if the Location table is empty
    location_count = db_session.query(Location).count()
    if location_count == 0:
        # Load gazetteer data from a predefined source
        gazetteer_data = pd.read_csv(GAZETTEER_PATH).to_dict(orient="records")
        
        for loc in gazetteer_data:
            location = Location(name_he=loc["name_he"], name_en=loc["name_en"])
            db_session.add(location)

        db_session.commit()

# Initialize any resources needed by the processing system
def initialize_processing():
    """
    Initializes the processing system by setting up necessary resources.
    Returns:
        None
    """
    # Placeholder for actual initialization logic
    pass