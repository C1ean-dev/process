import pytest
from flask import url_for
from app.models import File, User
from tests.test_auth import login # Assuming login helper is in test_auth
from unittest.mock import patch, MagicMock, ANY
import os
import json
from io import BytesIO
from urllib.parse import urlparse # Import urlparse


def test_home_page_requires_login(client):
    """Test that the home page requires login."""
    response = client.get('/home')
    assert response.status_code == 302 # Redirect to login
    assert '/login' in response.headers['Location']

def test_home_page_logged_in(client, session, regular_user):
    """Test that the home page is accessible after login."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])
    response = client.get(url_for('files.home'))
    assert response.status_code == 200
    assert b'Welcome to the File Processor!' in response.data
    assert regular_user.username.encode() in response.data

def test_upload_page_requires_login(client):
    """Test that the upload page requires login."""
    response = client.get(url_for('files.upload_file'))
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

@patch('app.mq.mq.publish_task')
@patch('app.files.handlers.os.remove')
@patch('flask.current_app')
def test_upload_file_success_single(mock_current_app, mock_os_remove, mock_publish_task, client, session, regular_user):
    """Test successful single file upload."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    mock_current_app.config = client.application.config

    data = {
        'file': (BytesIO(b'my file contents'), 'test_image.png')
    }

    response = client.post(
        url_for('files.upload_file'),
        data=data,
        content_type='multipart/form-data',
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b'1 file(s) uploaded successfully and added to processing queue!' in response.data
    assert session.query(File).count() == 1

    uploaded_file = session.query(File).first()
    assert uploaded_file.original_filename == 'test_image.png'
    assert uploaded_file.status == 'pending'
    assert uploaded_file.user_id == regular_user.id

    mock_publish_task.assert_called_once_with({
        'file_id': uploaded_file.id,
        'filepath': uploaded_file.filepath,
        'retries': uploaded_file.retries
    })
    # The filepath in the DB should now point to the UPLOAD_FOLDER path, as it's deleted after queuing
    assert uploaded_file.filepath.startswith(client.application.config['UPLOAD_FOLDER'])

@patch('app.mq.mq.publish_task')
@patch('app.files.handlers.os.remove')
@patch('flask.current_app')
def test_upload_file_success_multiple(mock_current_app, mock_os_remove, mock_publish_task, client, session, regular_user):
    """Test successful multiple file upload."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    mock_current_app.config = client.application.config

    data = {
        'file': [
            (BytesIO(b'file1'), 'test1.pdf'),
            (BytesIO(b'file2'), 'test2.jpg')
        ]
    }

    response = client.post(
        url_for('files.upload_file'),
        data=data,
        content_type='multipart/form-data',
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b'2 file(s) uploaded successfully and added to processing queue!' in response.data
    assert session.query(File).count() == 2
    assert mock_publish_task.call_count == 2

    uploaded_files = session.query(File).all()
    for uploaded_file in uploaded_files:
        assert uploaded_file.filepath.startswith(client.application.config['UPLOAD_FOLDER'])

def test_view_data_page_requires_login(client):
    """Test that the view data page requires login."""
    response = client.get(url_for('files.view_data'))
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

def test_view_data_page_logged_in(client, session, regular_user):
    """Test that the view data page is accessible after login."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    response = client.get(url_for('files.view_data'))
    assert response.status_code == 200
    assert b'Uploaded Files and Processed Data' in response.data

def test_view_data_display_files(client, session, regular_user):
    """Test that uploaded files are displayed on the data page."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])
    
    file1 = File(filename='file1.png', original_filename='doc1.png', filepath='/path/to/file1.png', user_id=regular_user.id, status='completed', nome='John Doe', matricula='12345')
    file2 = File(filename='file2.pdf', original_filename='report.pdf', filepath='/path/to/file2.pdf', user_id=regular_user.id, status='failed', nome='Jane Doe')
    session.add_all([file1, file2])
    session.commit()

    response = client.get(url_for('files.view_data'))
    assert response.status_code == 200
    assert b'doc1.png' in response.data
    print(response.data)
    assert b'<td>report.pdf</td>' in response.data
    assert b'completed' in response.data
    assert b'failed' in response.data
    assert b'John Doe' in response.data
    assert b'12345' in response.data

@pytest.mark.parametrize("filter_field, query_value, expected_in, expected_not_in", [
    ('nome', 'John', b'John Doe', b'Jane Smith'),
    ('matricula', '123', b'12345', b'67890'),
    ('equipamentos', 'Laptop', b'Laptop', b'Monitor'),
    ('imei_numbers', '12345', b'123456789012345', b'987654321098765'),
    ('patrimonio_numbers', 'P100', b'P1001', b'P2002')
])
def test_view_data_filters(client, session, regular_user, filter_field, query_value, expected_in, expected_not_in):
    """Test filtering data by various fields."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    file1 = File(
        filename='file1.pdf', original_filename='doc1.pdf', filepath='/path/to/doc1.pdf', user_id=regular_user.id, status='completed',
        nome='John Doe', matricula='12345', funcao='Software Engineer', empregador='TechCorp Inc.', rg='1234567-8', cpf='111.222.333-44',
        equipamentos=json.dumps([{'nome_equipamento': 'Laptop', 'imei': '123456789012345', 'patrimonio': 'P1001'}]),
        imei_numbers=json.dumps(['123456789012345']),
        patrimonio_numbers=json.dumps(['P1001']),
        processed_data='This document contains extracted text about John Doe.'
    )
    file2 = File(
        filename='file2.pdf', original_filename='doc2.pdf', filepath='/path/to/doc2.pdf', user_id=regular_user.id, status='completed',
        nome='Jane Smith', matricula='67890', funcao='Project Manager', empregador='Global Solutions', rg='9876543-2', cpf='555.666.777-88',
        equipamentos=json.dumps([{'nome_equipamento': 'Monitor', 'imei': '987654321098765', 'patrimonio': 'P2002'}]),
        imei_numbers=json.dumps(['987654321098765']),
        patrimonio_numbers=json.dumps(['P2002']),
        processed_data='This document contains other text about Jane Smith.'
    )
    session.add_all([file1, file2])
    session.commit()

    response = client.get(url_for('files.view_data', query=query_value, filter=filter_field))
    assert response.status_code == 200
    assert expected_in in response.data
    assert expected_in in response.data
    assert b'doc2.pdf' not in response.data
    assert f"Showing results for: <strong>{query_value}</strong>".encode() in response.data

def test_view_data_filter_no_match(client, session, regular_user):
    """Test filtering with no matching results."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])
    
    file1 = File(filename='file1.png', original_filename='invoice.png', filepath='/path/to/file1.png', user_id=regular_user.id, status='completed', nome='John Doe')
    session.add(file1)
    session.commit()

    response = client.get(url_for('files.view_data', query='nonexistent', filter='nome'))
    assert response.status_code == 200
    assert b'No files found.' in response.data
    assert b'invoice.png' not in response.data

@patch('app.workers.handlers.boto3.client')
def test_download_file_success(mock_boto3_client, client, session, admin_user):
    """Test successful file download from R2."""
    login_response = login(client, admin_user.email, 'adminpassword')
    client.get(login_response.headers['Location'])

    mock_s3_client = MagicMock()
    mock_boto3_client.return_value = mock_s3_client
    mock_s3_client.generate_presigned_url.return_value = 'http://mock-r2-url/test_file.pdf'

    file_record = File(filename='test_file.pdf', original_filename='original.pdf', filepath='http://mock-r2-url/test_file.pdf', user_id=admin_user.id, status='completed')
    session.add(file_record)
    session.commit()

    response = client.get(url_for('files.download_file', filename='test_file.pdf'))
    assert response.status_code == 302
    assert response.headers['Location'] == 'http://mock-r2-url/test_file.pdf'
    mock_boto3_client.assert_called_once()
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        'get_object',
        Params={'Bucket': client.application.config['CLOUDFLARE_R2_BUCKET_NAME'], 'Key': 'test_file.pdf'},
        ExpiresIn=60
    )

@patch('app.files.handlers.os.remove')
@patch('flask.current_app')
def test_upload_invalid_file_type(mock_current_app, mock_os_remove, client, session, regular_user):
    """Test upload of invalid file type."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    mock_current_app.config = client.application.config

    data = {
        'file': (BytesIO(b'invalid content'), 'test.txt')
    }

    response = client.post(
        url_for('files.upload_file'),
        data=data,
        content_type='multipart/form-data',
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b'Skipped invalid file: test.txt' in response.data
    assert session.query(File).count() == 0

def test_download_unauthorized_file(client, session, regular_user, admin_user):
    """Test unauthorized download attempt."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    # File belongs to admin
    file_record = File(filename='admin_file.pdf', original_filename='admin.pdf', filepath='/path/admin.pdf', user_id=admin_user.id, status='completed')
    session.add(file_record)
    session.commit()

    response = client.get(url_for('files.download_file', filename='admin_file.pdf'), follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to download this file.' in response.data

@patch('app.files.handlers.record_metric')
@patch('app.mq.mq.publish_task')
@patch('app.files.handlers.os.remove')
@patch('flask.current_app')
def test_upload_with_metrics(mock_current_app, mock_os_remove, mock_publish_task, mock_record_metric, client, session, regular_user):
    """Test upload records metrics."""
    login_response = login(client, regular_user.email, 'userpassword')
    client.get(login_response.headers['Location'])

    mock_current_app.config = client.application.config

    data = {
        'file': (BytesIO(b'file content'), 'metric_test.pdf')
    }

    response = client.post(
        url_for('files.upload_file'),
        data=data,
        content_type='multipart/form-data',
        follow_redirects=True
    )

    assert response.status_code == 200
    mock_record_metric.assert_called_with('file_upload', 1, {'user_id': regular_user.id, 'file_id': ANY})

@patch('multiprocessing.Process')
def test_worker_startup(mock_process, app):
    """Test worker processes are started."""
    from app import start_workers
    start_workers(app)
    # In test config, NUM_WORKERS=0, so no processes started
    assert mock_process.call_count == 0

@patch('threading.Thread')
def test_result_processing_thread(mock_thread, app):
    """Test result processing thread is started."""
    from app import start_workers
    start_workers(app)
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()
    mock_thread.return_value.daemon = True
