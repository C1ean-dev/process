import pytest
from app.models import User
from urllib.parse import urlparse

def test_initial_redirect_no_admin(client, session):
    """Test that the app redirects to setup if no admin exists."""
    response = client.get('/')
    assert response.status_code == 302
    assert '/setup' in response.headers['Location']

def test_initial_redirect_with_admin(client, session):
    """Test that the app redirects to login if an admin exists."""
    # Create an admin user for this test scenario
    admin_user_instance = User(username='testadmin', email='testadmin@example.com', is_admin=True)
    admin_user_instance.set_password('adminpassword')
    session.add(admin_user_instance)
    session.commit()

    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302
    assert urlparse(response.headers['Location']).path == urlparse('/auth/login').path

def test_setup_admin_get(client, session):
    """Test GET request to setup admin page."""
    response = client.get('/setup')
    assert response.status_code == 200
    assert b'Setup Admin Account' in response.data

def test_setup_admin_post_success(client, session):
    """Test successful admin creation."""
    response = client.post('/setup', data={
        'username': 'newadmin',
        'email': 'newadmin@example.com',
        'password': 'newadminpassword',
        'confirm_password': 'newadminpassword'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Admin account created successfully! Please log in.' in response.data
    assert b'Login' in response.data # Redirects to login page

    admin = session.query(User).filter_by(username='newadmin').first()
    assert admin is not None
    assert admin.is_admin is True

def test_setup_admin_post_already_exists(client, session, admin_user):
    """Test that setup page redirects if admin already exists."""
    response = client.post('/setup', data={
        'username': 'anotheradmin',
        'email': 'anotheradmin@example.com',
        'password': 'password',
        'confirm_password': 'password'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Admin user already exists. Please log in.' in response.data
    assert b'Login' in response.data
    assert session.query(User).filter_by(username='anotheradmin').first() is None
