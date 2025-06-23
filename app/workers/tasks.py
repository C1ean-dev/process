from __future__ import annotations
import os
import logging
from multiprocessing import Process, Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models import File
from app.config import Config
from app.workers.pdf_processing.extraction import normalize_text, extract_text_from_pdf, extract_data_from_text
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_r2_client():
    """Initializes and returns a Boto3 S3 client for Cloudflare R2."""
    if not all([Config.CLOUDFLARE_ACCOUNT_ID, Config.CLOUDFLARE_R2_ACCESS_KEY_ID,
                Config.CLOUDFLARE_R2_SECRET_ACCESS_KEY, Config.CLOUDFLARE_R2_BUCKET_NAME,
                Config.CLOUDFLARE_R2_ENDPOINT_URL]):
        logger.error("Cloudflare R2 credentials or bucket name are not fully configured.")
        return None
    
    try:
        s3_client = boto3.client(
            service_name='s3',
            endpoint_url=Config.CLOUDFLARE_R2_ENDPOINT_URL,
            aws_access_key_id=Config.CLOUDFLARE_R2_ACCESS_KEY_ID,
            aws_secret_access_key=Config.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
            region_name='auto' # R2 does not use regions in the traditional S3 sense, 'auto' is recommended
        )
        logger.info("Cloudflare R2 client initialized successfully.")
        return s3_client
    except Exception as e:
        logger.error(f"Error initializing R2 client: {e}", exc_info=True)
        return None

def _upload_file_to_r2(local_file_path: str, object_name: str) -> str | None:
    """Uploads a file to Cloudflare R2 and returns its public URL."""
    s3_client = _get_r2_client()
    if not s3_client:
        return None

    bucket_name = Config.CLOUDFLARE_R2_BUCKET_NAME
    try:
        s3_client.upload_file(local_file_path, bucket_name, object_name)
        object_url = f"{Config.CLOUDFLARE_R2_ENDPOINT_URL}/{bucket_name}/{object_name}"
        logger.info(f"File {local_file_path} uploaded to R2 as {object_name}. URL: {object_url}")
        return object_url
    except ClientError as e:
        logger.error(f"Failed to upload {local_file_path} to R2: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during R2 upload for {local_file_path}: {e}", exc_info=True)
        return None

def _get_db_session(db_uri: str) -> Session:
    """Helper to get a new SQLAlchemy session."""
    engine = create_engine(db_uri)
    Session = sessionmaker(bind=engine)
    return Session()

def _update_file_status_in_db(session: Session, file_id: int, status: str, retries: int, file_path: str = None, processed_data: str = None, structured_data: dict = None):
    """Updates the file record in the database."""
    try:
        file_record = session.query(File).get(file_id)
        if file_record:
            file_record.status = status
            file_record.retries = retries
            if file_path:
                file_record.filepath = file_path
            if processed_data is not None:
                file_record.processed_data = processed_data.strip()
            if structured_data is not None:
                file_record.structured_data = structured_data
            session.commit()
            logger.info(f"File ID {file_id} status updated to '{status}' in DB.")
        else:
            logger.warning(f"File record with ID {file_id} not found in DB for status update.")
    except Exception as db_e:
        session.rollback()
        logger.error(f"Error updating DB status for file ID {file_id}: {db_e}", exc_info=True)

def _move_file(source_path: str, destination_folder: str, filename: str) -> str:
    """Moves a file to a specified destination folder."""
    destination_path = os.path.join(destination_folder, filename)
    try:
        if os.path.exists(source_path):
            os.rename(source_path, destination_path)
            logger.info(f"File {filename} moved from {os.path.basename(os.path.dirname(source_path))} to {os.path.basename(destination_folder)}")
            return destination_path
        else:
            raise FileNotFoundError(f"File not found at {source_path}.")
    except Exception as e:
        logger.error(f"Error moving file {source_path} to {destination_folder}: {e}", exc_info=True)
        raise # Re-raise to be caught by the main processing logic

def _extract_and_structure_data(file_path: str) -> tuple[str, dict]:
    """Extracts raw text and structured data from a file."""
    file_extension = os.path.splitext(file_path)[1].lower()
    processed_data = ""
    extracted_structured_data = {}

    if file_extension == '.pdf':
        processed_data = extract_text_from_pdf(file_path)
        if not processed_data.strip():
            logger.warning(f"PDF extraction (direct or OCR) returned empty for file: {file_path}.")
    else:
        logger.warning(f"Unsupported file type for {file_path}")
        raise ValueError("Unsupported file type")

    if processed_data and processed_data.strip():
        extracted_structured_data = extract_data_from_text(normalize_text(processed_data))
    else:
        logger.warning(f"Final raw processed_data is empty or whitespace for file: {file_path}. No structured data extracted.")
        extracted_structured_data = {}
    
    return processed_data, extracted_structured_data

def _handle_processing_error(session: Session, file_id: int, original_file_path: str, current_retries: int, results_queue: Queue, error_message: str, new_file_path_on_error: str = None):
    """Handles errors during file processing, updates DB, and sends result."""
    new_retries = current_retries + 1
    final_file_path = new_file_path_on_error if new_file_path_on_error else original_file_path
    
    # Attempt to move the file to FAILED_FOLDER if it's still in processing or pending
    filename = os.path.basename(original_file_path)
    failed_path = os.path.join(Config.FAILED_FOLDER, filename)
    try:
        if os.path.exists(final_file_path):
            final_file_path = _move_file(final_file_path, Config.FAILED_FOLDER, filename)
        elif os.path.exists(original_file_path): # Fallback if it never made it to processing folder
            final_file_path = _move_file(original_file_path, Config.FAILED_FOLDER, filename)
        else:
            logger.warning(f"Could not find file {filename} to move to FAILED_FOLDER after error.")
            final_file_path = original_file_path # Keep original path if cannot move
    except Exception as move_e:
        logger.error(f"Error moving file to FAILED_FOLDER after error: {move_e}", exc_info=True)
        final_file_path = original_file_path # Keep original path if cannot move

    _update_file_status_in_db(session, file_id, 'failed', new_retries, final_file_path, error_message, {})
    results_queue.put((file_id, 'failed', error_message, new_retries, final_file_path, {}))
    logger.info(f"Worker {os.getpid()} sent failed result for file ID {file_id} to results queue.")

def process_file_task(file_id: int, file_path: str, current_retries: int, results_queue: Queue, db_uri: str):
    """
    Orchestrates the processing of a single file.
    Handles file movement, text extraction, data structuring, and database updates.
    """
    session = _get_db_session(db_uri)
    new_file_path = file_path # This will be updated as the file moves
    filename = os.path.basename(file_path)
    processed_data = ""
    extracted_structured_data = {}
    current_status = 'failed' # Default to failed, update to completed on success
    new_retries = current_retries

    try:
        logger.info(f"Worker {os.getpid()} attempting to process file ID: {file_id} from path: {file_path} (Attempt: {current_retries + 1})")
        
        # 1. Update DB status to 'processing'
        _update_file_status_in_db(session, file_id, 'processing', new_retries)

        # 2. Move file from PENDING_FOLDER to PROCESSING_FOLDER
        new_file_path = _move_file(file_path, Config.PROCESSING_FOLDER, filename)

        # 3. Extract text and structured data
        processed_data, extracted_structured_data = _extract_and_structure_data(new_file_path)
        
        current_status = 'completed' # Mark as completed if all steps above succeed

    except FileNotFoundError as e:
        error_msg = f"File not found during processing: {e}"
        logger.error(error_msg, exc_info=True)
        _handle_processing_error(session, file_id, file_path, current_retries, results_queue, error_msg, new_file_path)
        return # Exit early on critical file system error
    except ValueError as e: # For unsupported file types
        error_msg = f"File processing failed due to unsupported type: {e}"
        logger.error(error_msg, exc_info=True)
        _handle_processing_error(session, file_id, file_path, current_retries, results_queue, error_msg, new_file_path)
        return
    except Exception as e:
        error_msg = f"An unexpected error occurred during file processing: {e}"
        logger.error(error_msg, exc_info=True)
        _handle_processing_error(session, file_id, file_path, current_retries, results_queue, error_msg, new_file_path)
        return
    finally:
        session.close() # Ensure session is closed

    # 4. Handle final file destination (R2 or FAILED_FOLDER)
    final_file_path = new_file_path # Default to current path in case of R2 upload failure
    
    if current_status == 'completed':
        # Upload to R2
        r2_object_name = filename # Use filename as the object name in R2
        r2_url = _upload_file_to_r2(new_file_path, r2_object_name)
        
        if r2_url:
            final_file_path = r2_url # Store R2 URL in DB
            logger.info(f"File {filename} successfully uploaded to R2. Local file will be deleted.")
            # Delete local file from PROCESSING_FOLDER after successful R2 upload
            try:
                os.remove(new_file_path)
                logger.info(f"Local file {new_file_path} removed after R2 upload.")
            except Exception as e:
                logger.warning(f"Could not remove local file {new_file_path} after R2 upload: {e}")
        else:
            logger.error(f"Failed to upload file {filename} to R2. Moving to FAILED_FOLDER.")
            current_status = 'failed'
            new_retries += 1
            processed_data += "\nWarning: Failed to upload to Cloudflare R2."
            # If R2 upload fails, move to FAILED_FOLDER
            try:
                final_file_path = _move_file(new_file_path, Config.FAILED_FOLDER, filename)
            except Exception as e:
                logger.error(f"Error moving file to FAILED_FOLDER after R2 upload failure: {e}", exc_info=True)
                final_file_path = new_file_path # Keep processing path if move fails
    else: # current_status is 'failed'
        # Move to FAILED_FOLDER
        try:
            final_file_path = _move_file(new_file_path, Config.FAILED_FOLDER, filename)
        except Exception as e:
            logger.error(f"Error moving file to FAILED_FOLDER: {e}", exc_info=True)
            processed_data += f"\nWarning: Could not move file to FAILED_FOLDER: {e}"
            final_file_path = new_file_path # Keep processing path if move fails

    # 5. Update final status and data in DB
    session = _get_db_session(db_uri) # Re-open session for final update
    _update_file_status_in_db(session, file_id, current_status, new_retries, final_file_path, processed_data, extracted_structured_data)
    session.close()

    # 6. Send result back to the main application via the results queue
    results_queue.put((file_id, current_status, processed_data.strip(), new_retries, final_file_path, extracted_structured_data))
    logger.info(f"Worker {os.getpid()} sent result for file ID {file_id} to results queue. Final Status: {current_status}")

def worker_main(task_queue: Queue, results_queue: Queue, db_uri: str):
    """
    Main loop for a worker process.
    Continuously fetches tasks from the task_queue and processes them,
    sending results to the results_queue.
    """
    logger.info(f"Worker process started. PID: {os.getpid()}. Listening for tasks...")
    while True:
        try:
            file_id, file_path, current_retries = task_queue.get()
            if file_id is None:
                logger.info(f"Worker process {os.getpid()} received stop signal. Exiting.")
                break
            logger.info(f"Worker {os.getpid()} received task: File ID {file_id}, Path: {file_path}, Retries: {current_retries}")
            process_file_task(file_id, file_path, current_retries, results_queue, db_uri)
        except Exception as e:
            logger.error(f"Worker {os.getpid()} - Error in worker main loop: {e}", exc_info=True)
            session = _get_db_session(db_uri)
            _handle_processing_error(session, file_id if 'file_id' in locals() else None, file_path if 'file_path' in locals() else None, (current_retries + 1) if 'current_retries' in locals() else 0, results_queue, f"Worker main loop error: {e}", file_path if 'file_path' in locals() else None)
            session.close()

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    q = Queue()

    worker_process = Process(target=worker_main, args=(q, db_uri))
    worker_process.start()
