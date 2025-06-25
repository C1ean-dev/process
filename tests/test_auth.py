import pytest
from flask import url_for
from flask_login import current_user
from ..app.models import User

def login(client, email, password):
    """Helper function to log in a user."""
    return client.post('/login', data=dict(
        email=email,
        password=password
    ), follow_redirects=True)

def logout(client):
    """Helper function to log out a user."""
    return client.get('/logout', follow_redirects=True)

def test_login_page_access(client):
    """Test that the login page can be accessed."""
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data

def test_login_success(client, session, admin_user):
    """Test successful user login."""
    response = login(client, admin_user.email, 'adminpassword')
    assert response.status_code == 200
    assert b'Welcome to the File Processor!' in response.data # Redirects to home
    assert current_user.is_authenticated
    assert current_user.username == admin_user.username

def test_login_invalid_credentials(client, session, admin_user):
    """Test login with invalid password."""
    response = login(client, admin_user.email, 'wrongpassword')
    assert response.status_code == 200
    assert b'Login Unsuccessful. Please check email and password' in response.data
    assert not current_user.is_authenticated

def test_logout_success(client, session, admin_user):
    """Test successful user logout."""
    login(client, admin_user.email, 'adminpassword')
    response = logout(client)
    assert response.status_code == 200
    assert b'Login' in response.data # Redirects to login page
    assert not current_user.is_authenticated

def test_register_page_access_non_admin(client, session, regular_user):
    """Test that a non-admin cannot access the register page."""
    login(client, regular_user.email, 'userpassword')
    response = client.get('/register', follow_redirects=True)
    assert response.status_code == 200
    assert b'You do not have permission to register new users.' in response.data
    assert b'Welcome to the File Processor!' in response.data # Redirects to home

def test_register_page_access_admin(client, session, admin_user):
    """Test that an admin can access the register page."""
    login(client, admin_user.email, 'adminpassword')
    response = client.get('/register')
    assert response.status_code == 200
    assert b'Register New User' in response.data

def test_register_new_user_success(client, session, admin_user):
    """Test successful registration of a new user by an admin."""
    login(client, admin_user.email, 'adminpassword')
    response = client.post('/register', data=dict(
        username='newuser',
        email='newuser@example.com',
        password='newuserpassword',
        confirm_password='newuserpassword'
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'Account created successfully!' in response.data
    assert b'Login' in response.data # Redirects to login page

    new_user = session.query(User).filter_by(username='newuser').first()
    assert new_user is not None
    assert new_user.is_admin is False

def test_register_new_user_duplicate_username(client, session, admin_user, regular_user):
    """Test registration with a duplicate username."""
    login(client, admin_user.email, 'adminpassword')
    response = client.post('/register', data=dict(
        username=regular_user.username, # Duplicate username
        email='another@example.com',
        password='password',
        confirm_password='password'
    ))
    assert response.status_code == 200
    assert b'That username is taken. Please choose a different one.' in response.data

def test_register_new_user_duplicate_email(client, session, admin_user, regular_user):
    """Test registration with a duplicate email."""
    login(client, admin_user.email, 'adminpassword')
    response = client.post('/register', data=dict(
        username='anotheruser',
        email=regular_user.email, # Duplicate email
        password='password',
        confirm_password='password'
    ))
    assert response.status_code == 200
    assert b'That email is taken. Please choose a different one.' in response.data
