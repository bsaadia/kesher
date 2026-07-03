from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.location import Location

locations_bp = Blueprint('locations', __name__)

@locations_bp.route('/locations', methods=['GET'])
def get_locations():
    locations = g.db_session.execute(select(Location)).scalars().all()
    return jsonify([loc.to_dict() for loc in locations])