import pytest
from flask import url_for
from app.models import User
from urllib.parse import urlparse # Import urlparse

def login(client, email, password):
    """Helper function to log in a user."""
    return client.post(url_for('auth.login'), data=dict(
        email=email,
        password=password
    ), follow_redirects=False) # Changed to False

def logout(client):
    """Helper function to log out a user."""
    return client.get(url_for('auth.logout'), follow_redirects=True)

def test_login_page_access(client):
    """Test that the login page can be accessed."""
    response = client.get(url_for('auth.login'))
    assert response.status_code == 200
    assert b'Login' in response.data

def test_login_success(client, admin_user):
    """Test successful user login."""
    response = login(client, admin_user.email, 'adminpassword')
    assert response.status_code == 302 # Expect redirect
    # Extract path from url_for output for comparison
    expected_location = urlparse(url_for('files.home')).path
    assert expected_location == urlparse(response.headers['Location']).path
    # Follow redirect and check content
    response = client.get(response.headers['Location'])
    assert response.status_code == 200
    assert b'Welcome to the File Processor!' in response.data

def test_logout_success(client, admin_user):
    """Test successful user logout."""
    # First, log in the user
    login_response = login(client, admin_user.email, 'adminpassword')
    # Follow the redirect to home page
    client.get(login_response.headers['Location'])

    response = logout(client)
    assert response.status_code == 200
    assert b'Login' in response.data # Redirects to login page

def test_register_page_access_admin(client, admin_user):
    """Test that an admin can access the register page."""
    login_response = login(client, admin_user.email, 'adminpassword')
    client.get(login_response.headers['Location'])

    response = client.get(url_for('auth.register'))
    assert response.status_code == 200
    assert b'Register New User' in response.data

def test_register_new_user_success(client, session, admin_user):
    """Test successful registration of a new user by an admin."""
    login_response = login(client, admin_user.email, 'adminpassword')
    client.get(login_response.headers['Location'])

    response = client.post(url_for('auth.register'), data=dict(
        username='newuser',
        email='newuser@example.com',
        password='newuserpassword',
        confirm_password='newuserpassword'
    ), follow_redirects=False) # Do not follow redirects
    assert response.status_code == 302 # Expect a redirect
    expected_location = urlparse(url_for('auth.login')).path
    assert expected_location == urlparse(response.headers['Location']).path

    # Follow the redirect to the login page and check its content
    response = client.get(response.headers['Location'], follow_redirects=True)
    assert response.status_code == 200
    assert b'Account created successfully!' in response.data

    new_user = session.query(User).filter_by(username='newuser').first()
    assert new_user is not None
    assert new_user.is_admin is False
