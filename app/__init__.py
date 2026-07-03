from flask import Flask, g
from sqlalchemy.orm import sessionmaker
from models.base import engine # Import the engine
import app.config

# Step 4: DB Session Lifecycle
# The tutorial shows creating a Session factory
Session = sessionmaker(bind=engine)

def setup_db_session(app):
    @app.before_request
    def open_db_session():
        """Open DB session at request start"""
        g.db_session = Session()

    @app.teardown_appcontext
    def close_db_session(exception=None):
        """Close DB session at request end"""
        session = g.pop('db_session', None)
        if session is not None:
            if exception is None:
                try:
                    session.commit()
                except Exception:
                    session.rollback()
            else:
                session.rollback()
            session.close()

def create_app():
    """
    Create a Flask application using the app factory pattern.
    """
    # Step 1: Create the Flask instance
    app = Flask(__name__)

    # Step 2: Load configuration
    app.config.from_object('app.config')
    # The DB URL is currently hardcoded in models/message.py
    # For a more flexible app, it should be in the config file.

    # Step 3: Register blueprints
    # Blueprints for messages, locations, and admin would be imported and registered here.
    from app.routes.messages import messages_bp
    from app.routes.associations import associations_bp
    from app.routes.locations import locations_bp
    from app.routes.map import map_bp
    from app.routes.ridgeline import ridgeline_bp
    app.register_blueprint(messages_bp)
    app.register_blueprint(associations_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(ridgeline_bp)

    # Step 3b: Mount embedded Dash apps onto the Flask server
    from app.dash_apps.explore import init_explore_dash
    init_explore_dash(app)

    # Step 4: Attach DB session lifecycle
    setup_db_session(app)

    # Step 5: Return the app
    return app
