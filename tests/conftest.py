import pytest
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, shutdown_workers
from app.models import db, User, File
from app.config import Config

# Use an in-memory SQLite database for testing
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    WTF_CSRF_ENABLED = False # Disable CSRF for easier testing
    # Make sure workers don't actually start
    NUM_WORKERS = 0
    # Use test folders
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'test_uploads')
    PENDING_FOLDER = os.path.join(os.getcwd(), 'test_aguardando_processo')
    PROCESSING_FOLDER = os.path.join(os.getcwd(), 'test_processando')
    COMPLETED_FOLDER = os.path.join(os.getcwd(), 'test_completos')
    FAILED_FOLDER = os.path.join(os.getcwd(), 'test_falhas')
    # Add dummy R2 config for tests
    CLOUDFLARE_R2_BUCKET_NAME = 'test-bucket'
    CLOUDFLARE_R2_ENDPOINT_URL = 'https://test.r2.dev'
    CLOUDFLARE_ACCOUNT_ID = 'test-account-id'
    CLOUDFLARE_R2_ACCESS_KEY_ID = 'test-key-id'
    CLOUDFLARE_R2_SECRET_ACCESS_KEY = 'test-secret-key'

@pytest.fixture(scope='function')
def app():
    """Create and configure a new app instance for each test."""
    _app = create_app()
    _app.config.from_object(TestConfig)
    _app.config['SERVER_NAME'] = 'localhost'

    # Create test folders
    for folder in ['UPLOAD_FOLDER', 'PENDING_FOLDER', 'PROCESSING_FOLDER', 'COMPLETED_FOLDER', 'FAILED_FOLDER']:
        os.makedirs(_app.config[folder], exist_ok=True)

    with _app.app_context():
        db.create_all()
        

        yield _app
        # Explicitly shut down any worker-related threads
        shutdown_workers(_app)
        db.drop_all()

    # Clean up test folders
    for folder in ['UPLOAD_FOLDER', 'PENDING_FOLDER', 'PROCESSING_FOLDER', 'COMPLETED_FOLDER', 'FAILED_FOLDER']:
        folder_path = _app.config[folder]
        if os.path.exists(folder_path):
            for f in os.listdir(folder_path):
                try:
                    os.remove(os.path.join(folder_path, f))
                except OSError:
                    pass # Ignore errors if file is gone
            try:
                os.rmdir(folder_path)
            except OSError:
                pass # Ignore errors if dir is not empty

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
        yield db.session
        db.session.remove()

@pytest.fixture(scope='function')
def admin_user(session):
    """Creates an admin user for testing."""
    # This fixture now assumes an admin user might already exist from the app fixture
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