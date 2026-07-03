from flask import Blueprint, render_template, jsonify, g
from sqlalchemy import select, distinct
from models.message import Message
from models.associations import MessageLocation
from models.location import Location

ridgeline_bp = Blueprint('ridgeline', __name__)

@ridgeline_bp.route('/ridgeline')
def ridgeline():
    return render_template('ridgeline.html')

@ridgeline_bp.route('/ridgeline-data')
def ridgeline_data():
    db_session = g.db_session
    # One row per (message, front) pair — a message can span multiple fronts
    query = (
        select(Message.timestamp, Location.front)
        .join(MessageLocation, Message.id == MessageLocation.message_id)
        .join(Location, MessageLocation.location_id == Location.id)
        .where(Location.front.isnot(None))
        .distinct()
    )
    rows = db_session.execute(query).all()
    return jsonify([
        {"timestamp": ts.isoformat(), "front": front}
        for ts, front in rows
        if ts is not None
    ])
