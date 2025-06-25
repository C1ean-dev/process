import pytest
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.models import db, User, File
from app.config import Config

# Use an in-memory SQLite database for testing
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    WTF_CSRF_ENABLED = False # Disable CSRF for easier testing
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'test_uploads')
    PROCESSED_FOLDER = os.path.join(os.getcwd(), 'test_aguardando_processo')

@pytest.fixture(scope='session')
def app():
    """Create and configure a new app instance for each test session."""
    _app = create_app()
    _app.config.from_object(TestConfig)

    # Ensure test folders exist
    os.makedirs(_app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(_app.config['PROCESSED_FOLDER'], exist_ok=True)

    with _app.app_context():
        db.create_all()
        yield _app
        db.drop_all()

    # Clean up test folders after session
    if os.path.exists(_app.config['UPLOAD_FOLDER']):
        for f in os.listdir(_app.config['UPLOAD_FOLDER']):
            os.remove(os.path.join(_app.config['UPLOAD_FOLDER'], f))
        os.rmdir(_app.config['UPLOAD_FOLDER'])
    if os.path.exists(_app.config['PROCESSED_FOLDER']):
        for f in os.listdir(_app.config['PROCESSED_FOLDER']):
            os.remove(os.path.join(_app.config['PROCESSED_FOLDER'], f))
        os.rmdir(_app.config['PROCESSED_FOLDER'])


@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture(scope='function')
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()

@pytest.fixture(scope='function')
def session(app):
    """Provides a clean database session for each test."""
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        options = dict(bind=connection, binds={})
        session = db.create_scoped_session(options=options)
        db.session = session
        yield session
        transaction.rollback()
        connection.close()
        session.remove()

@pytest.fixture(scope='function')
def admin_user(session):
    """Creates an admin user for testing."""
    user = User(username='admin_test', email='admin@example.com', is_admin=True)
    user.set_password('adminpassword')
    session.add(user)
    session.commit()
    return user

@pytest.fixture(scope='function')
def regular_user(session):
    """Creates a regular user for testing."""
    user = User(username='user_test', email='user@example.com', is_admin=False)
    user.set_password('userpassword')
    session.add(user)
    session.commit()
    return user
