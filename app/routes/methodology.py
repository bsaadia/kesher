from flask import Blueprint, render_template

methodology_bp = Blueprint('methodology', __name__)

@methodology_bp.route('/methodology')
def methodology():
    return render_template('methodology.html')
