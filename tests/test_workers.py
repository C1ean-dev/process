import pytest
import os
from unittest.mock import patch, MagicMock
from ..app.workers.tasks import process_file_task, worker_main
from ..app.models import File
from multiprocessing import Queue

@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session for worker tests."""
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.get.return_value = MagicMock(spec=File) # Mock a File object
    return mock_session

@pytest.fixture
def mock_create_engine():
    """Mock create_engine and sessionmaker for worker tests."""
    with patch('workers.worker.create_engine') as mock_engine:
        with patch('workers.worker.sessionmaker') as mock_sessionmaker:
            mock_session = MagicMock()
            mock_sessionmaker.return_value.return_value = mock_session
            yield mock_engine, mock_sessionmaker, mock_session

@patch('workers.worker.pytesseract.image_to_string')
@patch('workers.worker.Image.open')
def test_process_image_file_success(mock_image_open, mock_image_to_string, mock_create_engine, session):
    """Test successful image processing by worker."""
    mock_engine, mock_sessionmaker, mock_session = mock_create_engine

    # Create a dummy file record in the test database
    test_file = File(filename='test.png', original_filename='test.png', filepath='/fake/path/test.png', user_id=1, status='pending')
    session.add(test_file)
    session.commit()

    # Configure the mock session to return our test_file
    mock_session.query.return_value.get.return_value = test_file

    mock_image_to_string.return_value = "Extracted text from image."
    mock_image_open.return_value = MagicMock() # Mock the opened image object

    process_file_task(test_file.id, test_file.filepath, 'sqlite:///:memory:')

    # Assertions on the mock session
    mock_session.query.return_value.get.assert_called_with(test_file.id)
    assert test_file.status == 'completed'
    assert test_file.processed_data == "Extracted text from image."
    mock_session.commit.assert_called()
    mock_session.close.assert_called()
    mock_image_open.assert_called_once_with(test_file.filepath)
    mock_image_to_string.assert_called_once()

@patch('workers.worker.PdfReader')
def test_process_pdf_file_success(mock_pdf_reader, mock_create_engine, session):
    """Test successful PDF processing by worker."""
    mock_engine, mock_sessionmaker, mock_session = mock_create_engine

    test_file = File(filename='test.pdf', original_filename='test.pdf', filepath='/fake/path/test.pdf', user_id=1, status='pending')
    session.add(test_file)
    session.commit()

    mock_session.query.return_value.get.return_value = test_file

    # Mock PdfReader and its pages
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Text from page 1."
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Text from page 2."
    
    mock_pdf_reader.return_value = MagicMock(pages=[mock_page1, mock_page2])

    process_file_task(test_file.id, test_file.filepath, 'sqlite:///:memory:')

    assert test_file.status == 'completed'
    assert test_file.processed_data == "Text from page 1.\nText from page 2."
    mock_session.commit.assert_called()
    mock_session.close.assert_called()
    mock_pdf_reader.assert_called_once_with(test_file.filepath)
    mock_page1.extract_text.assert_called_once()
    mock_page2.extract_text.assert_called_once()

@patch('workers.worker.pytesseract.image_to_string', side_effect=Exception("OCR Error"))
@patch('workers.worker.Image.open')
def test_process_file_failure(mock_image_open, mock_image_to_string, mock_create_engine, session):
    """Test file processing failure by worker."""
    mock_engine, mock_sessionmaker, mock_session = mock_create_engine

    test_file = File(filename='fail.png', original_filename='fail.png', filepath='/fake/path/fail.png', user_id=1, status='pending')
    session.add(test_file)
    session.commit()

    mock_session.query.return_value.get.return_value = test_file

    mock_image_open.return_value = MagicMock()

    process_file_task(test_file.id, test_file.filepath, 'sqlite:///:memory:')

    assert test_file.status == 'failed'
    assert "Error processing image: OCR Error" in test_file.processed_data
    mock_session.commit.assert_called()
    mock_session.close.assert_called()

@patch('workers.worker.process_file_task')
def test_worker_main_stops_on_sentinel(mock_process_file_task, mock_create_engine):
    """Test that worker_main stops when sentinel value is received."""
    mock_engine, mock_sessionmaker, mock_session = mock_create_engine
    
    q = Queue()
    q.put((1, '/fake/path/file.png')) # A dummy task
    q.put((None, None)) # Sentinel to stop

    worker_main(q, 'sqlite:///:memory:')

    mock_process_file_task.assert_called_once_with(1, '/fake/path/file.png', 'sqlite:///:memory:')
    assert q.empty() # Ensure queue is empty after processing and sentinel
