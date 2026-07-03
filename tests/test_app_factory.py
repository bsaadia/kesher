import pytest
from app import create_app
from flask import Flask

def test_create_app():
    """Test that the app factory creates a valid Flask app instance."""
    app = create_app()
    assert isinstance(app, Flask)
    assert app.name == 'app'

def test_config_loading():
    """Test that the app loads configuration correctly from app.config."""
    app = create_app()
    
    # Verify that keys defined in app/config.py are present in the app config
    # Note: We check for presence of keys. Values might be None depending on .env
    assert 'TELEGRAM_API_ID' in app.config
    assert 'TELEGRAM_API_HASH' in app.config
    assert 'TELEGRAM_PHONE' in app.config

def test_db_session_teardown_registered():
    """Test that the database session teardown function is registered."""
    app = create_app()
    # Check if close_db_session is in the teardown functions
    # The function name is 'close_db_session' inside setup_db_session
    teardown_funcs = [func.__name__ for func in app.teardown_appcontext_funcs]
    assert 'close_db_session' in teardown_funcs
