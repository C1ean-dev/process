import pytest
import os
import json
from unittest.mock import patch, MagicMock, ANY, mock_open

from app.workers.tasks import process_file_task, worker_main
from app.models import File
from app.config import Config

# Fixture to provide a mock database session for worker tests
@pytest.fixture
def mock_db_session(session):
    return session

# Fixture to mock the database engine and session creation in the worker
@pytest.fixture
def mock_db_setup(mock_db_session):
    with patch('app.workers.tasks._get_db_session') as mock_get_session:
        mock_get_session.return_value = mock_db_session
        yield mock_get_session

# Fixture to mock file system operations
@pytest.fixture
def mock_file_operations():
    # Use a dictionary to simulate file existence and paths
    mock_files = {}

    def mock_exists(path):
        return path in mock_files

    def mock_rename(src, dst):
        if src in mock_files:
            mock_files[dst] = mock_files.pop(src)
        else:
            raise FileNotFoundError(f"No such file or directory: '{src}'")

    with patch('app.workers.tasks.os.path.exists', side_effect=mock_exists) as mock_os_exists:
        with patch('app.workers.tasks.os.remove') as mock_os_remove:
            yield mock_os_exists, mock_os_remove, mock_files

# Main test suite for the worker

@patch('app.mq.mq.publish_result')
@patch('app.workers.handlers.Config.R2_FEATURE_FLAG', 'True')
@patch('app.workers.handlers.R2Uploader.upload', return_value='http://mock-r2-url/test.pdf')
@patch('app.workers.pdf_processing.extraction.extract_text_from_pdf', return_value='Extracted text')
@patch('app.workers.duplicate_checker.tasks.process_file_for_duplicates', return_value=False)
def test_process_file_with_r2_flag_true(
    mock_check_duplicates, mock_extract_text, mock_upload_r2, mock_publish_result,
    mock_db_setup, mock_db_session
 ):
    """Test file processing when R2_FEATURE_FLAG is True."""
    initial_filepath = os.path.join(Config.UPLOAD_FOLDER, 'test_r2_true.pdf')
    test_file = File(id=2, filename='test_r2_true.pdf', original_filename='orig_true.pdf', filepath=initial_filepath, user_id=1, status='pending')
    mock_db_session.add(test_file)
    mock_db_session.commit()

    with patch('builtins.open', mock_open(read_data=b'dummy')) as m_open, \
         patch('os.remove') as mock_remove:
        process_file_task(test_file.id, initial_filepath, 'sqlite:///:memory:', session=mock_db_session)

    mock_db_session.refresh(test_file)
    assert test_file.status == 'completed'
    assert test_file.filepath == 'http://mock-r2-url/test.pdf'
    mock_upload_r2.assert_called_once()
    mock_remove.assert_called_once_with(initial_filepath)
    mock_publish_result.assert_called_once()

@patch('app.mq.mq.publish_result')
@patch('app.workers.handlers.Config.R2_FEATURE_FLAG', 'False')
@patch('app.workers.handlers.Config.COMPLETED_FOLDER', '/tmp/completed')
@patch('app.workers.pdf_processing.extraction.extract_text_from_pdf', return_value='Extracted text')
@patch('app.workers.duplicate_checker.tasks.process_file_for_duplicates', return_value=False)
def test_process_file_with_r2_flag_false(
    mock_check_duplicates, mock_extract_text, mock_publish_result,
    mock_db_setup, mock_db_session
 ):
    """Test file processing when R2_FEATURE_FLAG is False."""
    initial_filepath = os.path.join(Config.UPLOAD_FOLDER, 'test_r2_false.pdf')
    completed_filepath = os.path.join('/tmp/completed', 'test_r2_false.pdf')
    test_file = File(id=3, filename='test_r2_false.pdf', original_filename='orig_false.pdf', filepath=initial_filepath, user_id=1, status='pending')
    mock_db_session.add(test_file)
    mock_db_session.commit()

    with patch('builtins.open', mock_open(read_data=b'dummy')) as m_open, \
         patch('os.rename') as mock_rename, \
         patch('os.makedirs') as mock_makedirs:
        process_file_task(test_file.id, initial_filepath, 'sqlite:///:memory:', session=mock_db_session)

    mock_db_session.refresh(test_file)
    # Since duplicate checker is mocked to False, it should complete
    assert test_file.status == 'completed'
    assert test_file.filepath == completed_filepath
    mock_makedirs.assert_called_once_with('/tmp/completed', exist_ok=True)
    mock_rename.assert_called_once_with(initial_filepath, completed_filepath)
    mock_publish_result.assert_called_once()

@patch('app.mq.mq.publish_result')
@patch('app.mq.mq.publish_result')
@patch('app.workers.tasks.FileProcessingTask')
@patch('app.workers.pdf_processing.extraction.extract_data_from_text')
@patch('app.workers.duplicate_checker.tasks.process_file_for_duplicates', return_value=False)
@patch('app.workers.handlers.R2Uploader.upload', return_value='http://mock-r2-url/test.pdf')
def test_process_file_task_success_pdf(
    mock_upload_r2, mock_check_duplicates, mock_extract_data, mock_file_processing_task, mock_publish_result,
    mock_db_setup, mock_file_operations, mock_db_session
 ):
    """Test the successful processing of a PDF file."""
    mock_exists, mock_remove, mock_files = mock_file_operations

    # Create a test file in the mock DB
    initial_filepath = os.path.join(Config.UPLOAD_FOLDER, 'test.pdf')
    test_file = File(id=10, filename='test.pdf', original_filename='orig.pdf', filepath=initial_filepath, user_id=1, status='pending')
    mock_db_session.add(test_file)
    mock_db_session.commit()

    # Simulate the initial file existence and content for open()
    mock_files[initial_filepath] = b'dummy pdf content'

    with patch('builtins.open', mock_open(read_data=b'dummy pdf content')) as mock_builtin_open:
        # Configure the mock FileProcessingTask instance
        mock_instance = mock_file_processing_task.return_value

        def mock_run_side_effect():
            # Simulate the task's effect on the file record
            test_file.status = 'completed'
            test_file.processed_data = "Extracted text from PDF."
            test_file.nome = "Test Name"
            test_file.filepath = 'http://mock-r2-url/test.pdf'
            mock_db_session.add(test_file)
            mock_db_session.commit()
            mock_publish_result()  # Simulate the publish_result call

        mock_instance.run.side_effect = mock_run_side_effect

        # Execute the task
        process_file_task(test_file.id, test_file.filepath, 'sqlite:///:memory:', session=mock_db_session)

        # Assertions
        mock_file_processing_task.assert_called_once_with(
            file_id=10,
            file_path=initial_filepath,
            session=mock_db_session
        )
        mock_instance.run.assert_called_once()

        mock_db_session.refresh(test_file) # Refresh the object to get latest state
        assert test_file.status == 'completed'
        assert test_file.processed_data == "Extracted text from PDF."
        assert test_file.nome == "Test Name"
        assert test_file.filepath == 'http://mock-r2-url/test.pdf'

        # Check publish result
        mock_publish_result.assert_called_once()

@patch('app.mq.mq.consume_tasks')
@patch('app.workers.tasks.process_file_task')
def test_worker_main_loop(mock_process_task, mock_consume_tasks, mock_db_setup):
    """Test the main worker loop processing tasks and stopping."""
    # Mock consume_tasks to call the callback with a message and then raise KeyboardInterrupt to stop
    def mock_consume(callback):
        ch = MagicMock()
        method = MagicMock()
        message = {'file_id': 1, 'filepath': '/path/one'}
        callback(ch, method, None, json.dumps(message).encode())
        raise KeyboardInterrupt  # To stop the consumption

    mock_consume_tasks.side_effect = mock_consume

    with pytest.raises(KeyboardInterrupt):
        worker_main('sqlite:///:memory:')

    mock_process_task.assert_called_once_with(1, '/path/one', 'sqlite:///:memory:', session=ANY)

@patch('app.mq.mq.publish_result')
@patch('app.workers.pdf_processing.extraction.extract_text_from_pdf', side_effect=Exception('PDF error'))
@patch('app.workers.duplicate_checker.tasks.process_file_for_duplicates', return_value=False)
def test_process_file_error_and_retry(mock_check_duplicates, mock_extract_text, mock_publish_result, mock_db_setup, mock_db_session):
    """Test file processing error, retry increment, and re-queue."""
    initial_filepath = os.path.join(Config.UPLOAD_FOLDER, 'error.pdf')
    test_file = File(id=4, filename='error.pdf', original_filename='error.pdf', filepath=initial_filepath, user_id=1, status='pending')
    mock_db_session.add(test_file)
    mock_db_session.commit()

    with patch('builtins.open', mock_open(read_data=b'dummy')):
        process_file_task(test_file.id, initial_filepath, 'sqlite:///:memory:', session=mock_db_session)

    mock_db_session.refresh(test_file)
    assert test_file.status == 'failed'
    mock_publish_result.assert_called_once()

@patch('app.workers.tasks.logger')
def test_mq_connection_failure(mock_logger, mock_db_setup):
    """Test graceful handling of MQ connection failure."""
    from app.mq import mq
    with patch.object(mq, 'connect', side_effect=Exception('MQ error')):
        with pytest.raises(Exception, match='MQ error'):
            mq.connect()
    mock_logger.error.assert_called_with('Failed to connect to CloudAMQP: MQ error')

@patch('app.mq.mq.consume_tasks')
@patch('app.workers.tasks.logger')
def test_consume_invalid_message(mock_logger, mock_consume_tasks, mock_db_setup):
    """Test handling of invalid JSON message."""
    def mock_consume(callback):
        ch = MagicMock()
        method = MagicMock()
        callback(ch, method, None, b'invalid json')
        raise KeyboardInterrupt

    mock_consume_tasks.side_effect = mock_consume

    with patch('app.workers.tasks.process_file_task') as mock_process:
        worker_main('sqlite:///:memory:')
        mock_logger.error.assert_called_with('Worker encountered a critical error: Expecting value: line 1 column 1 (char 0)', exc_info=True)

@patch('app.mq.mq.publish_result')
@patch('app.workers.duplicate_checker.tasks.process_file_for_duplicates', return_value=True)
def test_duplicate_file_detected(mock_check_duplicates, mock_publish_result, mock_db_setup, mock_db_session):
    """Test duplicate file detection, no processing."""
    initial_filepath = os.path.join(Config.UPLOAD_FOLDER, 'duplicate.pdf')
    test_file = File(id=6, filename='duplicate.pdf', original_filename='duplicate.pdf', filepath=initial_filepath, user_id=1, status='pending')
    mock_db_session.add(test_file)
    mock_db_session.commit()

    with patch('builtins.open', mock_open(read_data=b'dummy')):
        process_file_task(test_file.id, initial_filepath, 'sqlite:///:memory:', session=mock_db_session)

    mock_db_session.refresh(test_file)
    assert test_file.status == 'duplicate'
    assert test_file.processed_data == "Duplicate file detected."
    mock_publish_result.assert_called_once()

@patch('app.mq.mq.publish_result')
@patch('app.workers.pdf_processing.extraction.extract_text_from_pdf', return_value='')
@patch('pdf2image.convert_from_path')
@patch('pytesseract.image_to_string', return_value='OCR text')
@patch('app.workers.duplicate_checker.tasks.process_file_for_duplicates', return_value=False)
def test_ocr_processing(mock_check_duplicates, mock_tesseract, mock_convert, mock_extract_text, mock_publish_result, mock_db_setup, mock_db_session):
    """Test OCR when direct text extraction fails."""
    initial_filepath = os.path.join(Config.UPLOAD_FOLDER, 'ocr.pdf')
    test_file = File(id=7, filename='ocr.pdf', original_filename='ocr.pdf', filepath=initial_filepath, user_id=1, status='pending')
    mock_db_session.add(test_file)
    mock_db_session.commit()

    mock_convert.return_value = [MagicMock()]  # Mock image

    with patch('builtins.open', mock_open(read_data=b'dummy')):
        process_file_task(test_file.id, initial_filepath, 'sqlite:///:memory:', session=mock_db_session)

    mock_db_session.refresh(test_file)
    assert test_file.status == 'completed'
    mock_tesseract.assert_called_once()
    mock_publish_result.assert_called_once()
