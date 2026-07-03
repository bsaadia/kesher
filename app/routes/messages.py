from flask import Blueprint, jsonify, g
from models.db import MessageStorage

messages_bp = Blueprint('messages', __name__)

@messages_bp.route('/messages', methods=['GET'])
def get_messages():
    storage = MessageStorage(g.db_session)
    messages = storage.get_all_messages()
    
    # Use the to_dict method to serialize the objects
    results = [msg.to_dict() for msg in messages]
    return jsonify(results)