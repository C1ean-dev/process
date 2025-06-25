import pytest
from flask import url_for
from ..app.models import File
from tests.test_auth import login
from unittest.mock import patch, MagicMock
import os

def test_home_page_requires_login(client):
    """Test that the home page requires login."""
    response = client.get('/home')
    assert response.status_code == 302 # Redirect to login
    assert '/login' in response.headers['Location'] # Still redirects to auth.login

def test_home_page_logged_in(client, session, regular_user):
    """Test that the home page is accessible after login."""
    login(client, regular_user.email, 'userpassword')
    response = client.get(url_for('files.home')) # Updated url_for
    assert response.status_code == 200
    assert b'Welcome to the File Processor!' in response.data
    assert regular_user.username.encode() in response.data

def test_upload_page_requires_login(client):
    """Test that the upload page requires login."""
    response = client.get(url_for('files.upload_file')) # Updated url_for
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

@patch('main.os.rename')
@patch('main.file.save')
@patch('main.current_app')
def test_upload_file_success(mock_current_app, mock_file_save, mock_os_rename, client, session, regular_user):
    """Test successful file upload."""
    # Mock current_app.config
    mock_current_app.config = {
        'UPLOAD_FOLDER': 'test_uploads',
        'PROCESSED_FOLDER': 'test_aguardando_processo',
        'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif', 'pdf'},
        'TASK_QUEUE': MagicMock() # Mock the task queue
    }

    login(client, regular_user.email, 'userpassword')

    # Create a dummy file for upload
    from io import BytesIO
    data = {
        'file': (BytesIO(b"my file content"), 'test_image.png')
    }
    response = client.post(url_for('files.upload_file'), data=data, content_type='multipart/form-data', follow_redirects=True) # Updated url_for

    assert response.status_code == 200
    assert b'File uploaded successfully and added to processing queue!' in response.data
    assert session.query(File).count() == 1

    uploaded_file = session.query(File).first()
    assert uploaded_file.original_filename == 'test_image.png'
    assert uploaded_file.status == 'pending'
    
    # Verify file operations were called
    mock_file_save.assert_called_once()
    mock_os_rename.assert_called_once()
    mock_current_app.config['TASK_QUEUE'].put.assert_called_once_with(
        (uploaded_file.id, uploaded_file.filepath)
    )

@patch('main.current_app')
def test_upload_file_no_file_part(mock_current_app, client, session, regular_user):
    """Test upload with no file part in request."""
    mock_current_app.config = {
        'UPLOAD_FOLDER': 'test_uploads',
        'PROCESSED_FOLDER': 'test_aguardando_processo',
        'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif', 'pdf'},
        'TASK_QUEUE': MagicMock()
    }
    login(client, regular_user.email, 'userpassword')
    response = client.post(url_for('files.upload_file'), data={}, content_type='multipart/form-data', follow_redirects=True) # Updated url_for
    assert b'No file part' in response.data
    assert session.query(File).count() == 0

@patch('main.current_app')
def test_upload_file_no_selected_file(mock_current_app, client, session, regular_user):
    """Test upload with no file selected (empty filename)."""
    mock_current_app.config = {
        'UPLOAD_FOLDER': 'test_uploads',
        'PROCESSED_FOLDER': 'test_aguardando_processo',
        'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif', 'pdf'},
        'TASK_QUEUE': MagicMock()
    }
    login(client, regular_user.email, 'userpassword')
    from io import BytesIO
    data = {
        'file': (BytesIO(b""), '') # Empty filename
    }
    response = client.post(url_for('files.upload_file'), data=data, content_type='multipart/form-data', follow_redirects=True) # Updated url_for
    assert b'No selected file' in response.data
    assert session.query(File).count() == 0

@patch('main.current_app')
def test_upload_file_invalid_extension(mock_current_app, client, session, regular_user):
    """Test upload with an invalid file extension."""
    mock_current_app.config = {
        'UPLOAD_FOLDER': 'test_uploads',
        'PROCESSED_FOLDER': 'test_aguardando_processo',
        'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg', 'gif', 'pdf'},
        'TASK_QUEUE': MagicMock()
    }
    login(client, regular_user.email, 'userpassword')
    from io import BytesIO
    data = {
        'file': (BytesIO(b"my file content"), 'document.txt') # Invalid extension
    }
    response = client.post(url_for('files.upload_file'), data=data, content_type='multipart/form-data', follow_redirects=True) # Updated url_for
    assert b'Invalid file type. Allowed types are: png, jpg, jpeg, gif, pdf' in response.data
    assert session.query(File).count() == 0

def test_view_data_page_requires_login(client):
    """Test that the view data page requires login."""
    response = client.get(url_for('files.view_data')) # Updated url_for
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

def test_view_data_page_logged_in(client, session, regular_user):
    """Test that the view data page is accessible after login."""
    login(client, regular_user.email, 'userpassword')
    response = client.get(url_for('files.view_data')) # Updated url_for
    assert response.status_code == 200
    assert b'Uploaded Files and Processed Data' in response.data

def test_view_data_display_files(client, session, regular_user):
    """Test that uploaded files are displayed on the data page."""
    login(client, regular_user.email, 'userpassword')
    
    file1 = File(filename='file1.png', original_filename='doc1.png', filepath='/path/to/file1.png', user_id=regular_user.id, status='completed', processed_data='text from doc1')
    file2 = File(filename='file2.pdf', original_filename='report.pdf', filepath='/path/to/file2.pdf', user_id=regular_user.id, status='pending')
    session.add_all([file1, file2])
    session.commit()

    response = client.get(url_for('files.view_data')) # Updated url_for
    assert response.status_code == 200
    assert b'doc1.png' in response.data
    assert b'report.pdf' in response.data
    assert b'text from doc1' in response.data
    assert b'pending' in response.data

def test_view_data_filter_by_filename(client, session, regular_user):
    """Test filtering data by original filename."""
    login(client, regular_user.email, 'userpassword')
    
    file1 = File(filename='file1.png', original_filename='invoice.png', filepath='/path/to/file1.png', user_id=regular_user.id, status='completed', processed_data='invoice details')
    file2 = File(filename='file2.pdf', original_filename='report.pdf', filepath='/path/to/file2.pdf', user_id=regular_user.id, status='completed', processed_data='annual report')
    session.add_all([file1, file2])
    session.commit()

    response = client.get(url_for('files.view_data', query='invoice')) # Updated url_for
    assert response.status_code == 200
    assert b'invoice.png' in response.data
    assert b'report.pdf' not in response.data
    assert b"Showing results for 'invoice'" in response.data

def test_view_data_filter_by_processed_data(client, session, regular_user):
    """Test filtering data by processed data content."""
    login(client, regular_user.email, 'userpassword')
    
    file1 = File(filename='file1.png', original_filename='invoice.png', filepath='/path/to/file1.png', user_id=regular_user.id, status='completed', processed_data='invoice details for client A')
    file2 = File(filename='file2.pdf', original_filename='report.pdf', filepath='/path/to/file2.pdf', user_id=regular_user.id, status='completed', processed_data='annual report for client B')
    session.add_all([file1, file2])
    session.commit()

    response = client.get(url_for('files.view_data', query='client B')) # Updated url_for
    assert response.status_code == 200
    assert b'invoice.png' not in response.data
    assert b'report.pdf' in response.data
    assert b"Showing results for 'client B'" in response.data

def test_view_data_filter_no_match(client, session, regular_user):
    """Test filtering with no matching results."""
    login(client, regular_user.email, 'userpassword')
    
    file1 = File(filename='file1.png', original_filename='invoice.png', filepath='/path/to/file1.png', user_id=regular_user.id, status='completed', processed_data='invoice details')
    session.add(file1)
    session.commit()

    response = client.get(url_for('files.view_data', query='nonexistent')) # Updated url_for
    assert response.status_code == 200
    assert b'No files found.' in response.data
    assert b'invoice.png' not in response.data

def test_worker_status_page_requires_login(client):
    """Test that the worker status page requires login."""
    response = client.get(url_for('workers.worker_status')) # Updated url_for
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

def test_worker_status_page_logged_in(client, session, regular_user):
    """Test that the worker status page is accessible after login."""
    login(client, regular_user.email, 'userpassword')
    response = client.get(url_for('workers.worker_status')) # Updated url_for
    assert response.status_code == 200
    assert b'Worker Status' in response.data

def test_worker_status_counts(client, session, regular_user):
    """Test that worker status page displays correct counts."""
    login(client, regular_user.email, 'userpassword')

    file_pending = File(filename='p.png', original_filename='p.png', filepath='/p.png', user_id=regular_user.id, status='pending')
    file_processing = File(filename='pr.png', original_filename='pr.png', filepath='/pr.png', user_id=regular_user.id, status='processing')
    file_completed = File(filename='c.png', original_filename='c.png', filepath='/c.png', user_id=regular_user.id, status='completed')
    file_failed = File(filename='f.png', original_filename='f.png', filepath='/f.png', user_id=regular_user.id, status='failed')
    session.add_all([file_pending, file_processing, file_completed, file_failed])
    session.commit()

    response = client.get(url_for('workers.worker_status')) # Updated url_for
    assert response.status_code == 200
    assert b'Pending Tasks</h5>\n                            <h5 class="card-title">1' in response.data
    assert b'Processing Tasks</h5>\n                            <h5 class="card-title">1' in response.data
    assert b'Completed Tasks</h5>\n                            <h5 class="card-title">1' in response.data
    assert b'Failed Tasks</h5>\n                            <h5 class="card-title">1' in response.data
