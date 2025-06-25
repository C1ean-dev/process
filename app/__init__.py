import json
import os
import logging

from flask import Flask, redirect, url_for, flash, render_template, request
from .config import Config # Changed to relative import
from .models import db, User, File # Import File model
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user
from multiprocessing import Process, Queue
from .workers.tasks import worker_main # Import the worker function from its new path
import atexit # For graceful shutdown
import threading # Import threading for Event
import json # Import json for structured data serialization

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)



def from_json(value):
    """Jinja2 filter to parse JSON strings."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value # Return original value if not valid JSON


# Global queues and worker processes list
task_queue = Queue() # For sending tasks to workers
results_queue = Queue() # For receiving results from workers
worker_processes = []
NUM_WORKERS = os.cpu_count() - 2 # Number of worker processes to run
folder_monitor_stop_event = threading.Event() # Event to signal folder monitor to stop

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    CSRFProtect(app)

    login_manager = LoginManager()
    login_manager.init_app(app)

    # Register the custom Jinja2 filter
    app.jinja_env.filters['from_json'] = from_json
    login_manager.login_view = 'auth.login' # Redirect to login page if not authenticated

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Create upload and processed folders if they don't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PENDING_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PROCESSING_FOLDER'], exist_ok=True)
    os.makedirs(app.config['COMPLETED_FOLDER'], exist_ok=True)
    os.makedirs(app.config['FAILED_FOLDER'], exist_ok=True)

    with app.app_context():
        db.create_all()

        # Check if an admin user exists, if not, redirect to setup
        if User.query.filter_by(is_admin=True).first() is None:
            logger.info("No admin user found. Redirecting to setup.")
            @app.route('/')
            def initial_redirect():
                return redirect(url_for('setup.setup_admin'))
        else:
            logger.info("Admin user already exists. Normal application flow.")
            # If admin exists, set the default route to login or home
            @app.route('/')
            def initial_redirect():
                return redirect(url_for('auth.login')) # Assuming 'auth' blueprint and 'login' route

        # Store the task queue and db_uri in app config for access in blueprints
        app.config['TASK_QUEUE'] = task_queue
        app.config['RESULTS_QUEUE'] = results_queue # Store results queue in config
        app.config['DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI']

        # Import and register blueprints
        from app.auth import auth_bp
        from app.files import files_bp
        from app.init_register import setup_bp
        from app.workers import workers_bp # Import the new workers blueprint

        app.register_blueprint(auth_bp)
        app.register_blueprint(files_bp) # Register the new files blueprint
        app.register_blueprint(setup_bp)
        app.register_blueprint(workers_bp) # Register the new workers blueprint

    return app

def start_workers(app):
    """Starts the worker processes."""
    logger.info(f"Starting {NUM_WORKERS} worker processes...")
    for _ in range(NUM_WORKERS):
        # Pass both queues to the worker_main
        worker_process = Process(target=worker_main, args=(task_queue, results_queue, app.config['DATABASE_URI']))
        worker_process.daemon = True # Allow main program to exit even if workers are running
        worker_process.start()
        worker_processes.append(worker_process)
        logger.info(f"Worker process {worker_process.pid} started.")

    # Start a background thread to process results from workers
    from threading import Thread
    def process_results_from_queue(app_context):
        with app_context:
            # Import File model here to ensure it's available in the thread's context
            from .models import File
            while True:
                try:
                    # Now receiving file_id, new_status, processed_data, new_retries, new_file_path, and extracted_structured_data
                    file_id, new_status, processed_data, new_retries, new_file_path, extracted_structured_data = results_queue.get()
                    if file_id is None: # Sentinel to stop the thread
                        logger.info("Results processing thread received stop signal. Exiting.")
                        break
                    
                    file_record = db.session.query(File).get(file_id)
                    if file_record:
                        file_record.processed_data = processed_data
                        file_record.retries = new_retries # Update retry count

                        # Update structured data fields
                        file_record.nome = extracted_structured_data.get('nome')
                        file_record.matricula = extracted_structured_data.get('matricula')
                        file_record.funcao = extracted_structured_data.get('funcao')
                        file_record.empregador = extracted_structured_data.get('empregador')
                        file_record.rg = extracted_structured_data.get('rg')
                        file_record.cpf = extracted_structured_data.get('cpf')
                        file_record.data_documento = extracted_structured_data.get('data')
                        
                        # Convert equipments list to JSON string for storage
                        if 'equipamentos' in extracted_structured_data and extracted_structured_data['equipamentos'] is not None:
                            file_record.equipamentos = json.dumps(extracted_structured_data['equipamentos'])
                        else:
                            file_record.equipamentos = None

                        # New: Store IMEI and Patrimonio numbers as JSON strings
                        imei_list = extracted_structured_data.get('imei_numbers')
                        if imei_list is not None:
                            file_record.imei_numbers = json.dumps(imei_list)
                        else:
                            file_record.imei_numbers = None

                        patrimonio_list = extracted_structured_data.get('patrimonio_numbers')
                        if patrimonio_list is not None:
                            file_record.patrimonio_numbers = json.dumps(patrimonio_list)
                        else:
                            file_record.patrimonio_numbers = None


                        if new_status == 'failed' and new_retries < Config.MAX_RETRIES: # Use Config.MAX_RETRIES
                            file_record.status = 'retrying' # Set status to retrying
                            # The worker already moved the file to FAILED_FOLDER if it failed.
                            # We need to move it back to PENDING_FOLDER for retry.
                            filename = os.path.basename(new_file_path)
                            pending_path = os.path.join(Config.PENDING_FOLDER, filename)
                            try:
                                if os.path.exists(new_file_path): # Check if it's in FAILED_FOLDER
                                    os.rename(new_file_path, pending_path)
                                    file_record.filepath = pending_path # Update filepath in DB
                                    logger.info(f"File {filename} moved from {new_file_path} to {Config.PENDING_FOLDER} for retry.")
                                else:
                                    logger.warning(f"File {filename} not found at {new_file_path} for moving to {Config.PENDING_FOLDER} for retry. Assuming it's already there or lost.")
                                    # If file not found, keep original filepath in DB, but still re-queue
                                    file_record.filepath = new_file_path # Keep the last known path
                            except Exception as move_e:
                                logger.error(f"Error moving file {new_file_path} to {Config.PENDING_FOLDER} for retry: {move_e}")
                                file_record.filepath = new_file_path # Keep the last known path if move fails

                            try:
                                db.session.commit() # Commit status and filepath update
                                # Re-add to task queue for retry, using the updated filepath
                                task_queue.put((file_id, file_record.filepath, new_retries))
                                logger.info(f"Main app re-queued file {file_id} for retry (Attempt {new_retries + 1}/{Config.MAX_RETRIES}).")
                            except Exception as commit_e:
                                db.session.rollback()
                                logger.error(f"Error committing file status update for {file_id} during retry re-queue: {commit_e}", exc_info=True)
                        else:
                            file_record.status = new_status # Set final status (completed or failed after max retries)
                            file_record.filepath = new_file_path # Update filepath to the final folder (completed or failed)
                            try:
                                db.session.commit()
                                logger.info(f"Main app updated file {file_id} to final status '{new_status}' and filepath '{new_file_path}'.")
                            except Exception as commit_e:
                                db.session.rollback()
                                logger.error(f"Error committing file status update for {file_id} to final status: {commit_e}", exc_info=True)
                    else:
                        logger.warning(f"Main app could not find file {file_id} to update status.")
                except Exception as e:
                    logger.error(f"Error in results processing thread: {e}", exc_info=True)

    results_thread = Thread(target=process_results_from_queue, args=(app.app_context(),))
    results_thread.daemon = True
    results_thread.start()
    app.config['RESULTS_THREAD'] = results_thread # Store thread for potential management

    # Start the folder monitor thread
    folder_monitor_thread = Thread(target=start_folder_monitor, args=(app.app_context(), task_queue, folder_monitor_stop_event))
    folder_monitor_thread.daemon = True
    folder_monitor_thread.start()
    app.config['FOLDER_MONITOR_THREAD'] = folder_monitor_thread # Store thread for management

# Moved start_folder_monitor outside start_workers
def start_folder_monitor(app_context, task_queue, stop_event):
    """
    Monitors the PENDING_FOLDER for new or failed files and adds them to the task queue.
    """
    with app_context:
        from .models import File # Import File model within the app context
        from .files.routes import allowed_file # Import allowed_file for validation
        logger.info(f"Folder monitor started. Checking '{Config.PENDING_FOLDER}' every {Config.FOLDER_MONITOR_INTERVAL_SECONDS} seconds.")
        while not stop_event.is_set():
            try:
                for filename in os.listdir(Config.PENDING_FOLDER):
                    file_path = os.path.join(Config.PENDING_FOLDER, filename)
                    if os.path.isfile(file_path) and allowed_file(filename):
                        # Check if the file is already in the database
                        file_record = File.query.filter_by(filename=filename).first()

                        if file_record:
                            # If file exists in DB and is failed/retrying, re-queue it
                            if file_record.status in ['failed', 'retrying'] and file_record.retries < Config.MAX_RETRIES:
                                # Ensure the file is in PENDING_FOLDER before re-queueing
                                # It might be in FAILED_FOLDER if it failed previously
                                if os.path.exists(os.path.join(Config.FAILED_FOLDER, filename)):
                                    os.rename(os.path.join(Config.FAILED_FOLDER, filename), file_path)
                                    logger.info(f"File {filename} moved from FAILED_FOLDER to PENDING_FOLDER for retry.")
                                
                                task_queue.put((file_record.id, file_path, file_record.retries))
                                file_record.status = 'pending' # Reset status to pending for re-queue
                                db.session.commit()
                                logger.info(f"Folder monitor re-queued existing file {filename} (ID: {file_record.id}) for retry.")
                            # If file is pending/processing, do nothing (it's already in queue or being processed)
                            elif file_record.status in ['pending', 'processing']:
                                pass # Already handled by upload or previous re-queue
                            # If file is completed, do nothing
                            elif file_record.status == 'completed':
                                pass # Already processed
                        else:
                            # If file is new to the DB, add it and queue it
                            try:
                                # Attempt to find an admin user to associate the file with
                                admin_user = User.query.filter_by(is_admin=True).first()
                                if admin_user:
                                    new_file = File(
                                        filename=filename,
                                        original_filename=filename, # Use filename as original_filename for now
                                        filepath=file_path,
                                        user_id=admin_user.id,
                                        status='pending',
                                        retries=0
                                    )
                                    db.session.add(new_file)
                                    db.session.commit()
                                    task_queue.put((new_file.id, new_file.filepath, new_file.retries))
                                    logger.info(f"Folder monitor added new file {filename} to DB (ID: {new_file.id}) and queued for processing.")
                                else:
                                    logger.warning(f"File {filename} found in '{Config.PENDING_FOLDER}' but no admin user found to associate with. Skipping.")
                            except Exception as db_e:
                                db.session.rollback() # Rollback in case of error
                                logger.error(f"Error adding file {filename} from folder monitor to DB: {db_e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in folder monitor thread: {e}", exc_info=True)
            
            stop_event.wait(Config.FOLDER_MONITOR_INTERVAL_SECONDS) # Wait for interval or until stop signal

def shutdown_workers(app): # Accept app as argument
    """Sends stop signals to workers and joins them."""
    logger.info("Shutting down worker processes...")
    for _ in worker_processes:
        task_queue.put((None, None, None)) # Send sentinel value to stop each worker (now expects 3 args)
    
    # Send sentinel to results processing thread
    results_queue.put((None, None, None, None, None)) # Now expects 5 args

    # Signal folder monitor to stop
    folder_monitor_stop_event.set()
    if 'FOLDER_MONITOR_THREAD' in app.config and app.config['FOLDER_MONITOR_THREAD'].is_alive():
        app.config['FOLDER_MONITOR_THREAD'].join(timeout=5)
        if app.config['FOLDER_MONITOR_THREAD'].is_alive():
            logger.warning("Folder monitor thread did not terminate gracefully.")

    for worker_process in worker_processes:
        worker_process.join(timeout=5) # Give workers some time to finish
        if worker_process.is_alive():
            logger.warning(f"Worker process {worker_process.pid} did not terminate gracefully. Terminating.")
            worker_process.terminate()
    
    # Wait for results thread to finish
    if 'RESULTS_THREAD' in app.config and app.config['RESULTS_THREAD'].is_alive(): # Use app.config
        app.config['RESULTS_THREAD'].join(timeout=5) # Use app.config
        if app.config['RESULTS_THREAD'].is_alive():
            logger.warning("Results processing thread did not terminate gracefully.")

    logger.info("All worker processes, results thread, and folder monitor shut down.")
