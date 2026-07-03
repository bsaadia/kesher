from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.associations import MessageLocation
from models.message import Message
from models.location import Location

associations_bp = Blueprint('associations', __name__)

@associations_bp.route('/associations', methods=['GET'])

def get_associations():
    """
    Retrieves and returns all message-location associations.
    """
    db_session = g.db_session

    # Query to get all associations
    query = select(MessageLocation)
    query_results = db_session.execute(query).scalars().all()

    

    # Create a list of dictionaries for the JSON response
    associations = [
        association.to_dict() for association in query_results
    ]

    return jsonify(associations)
