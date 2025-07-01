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
    

    with app.app_context():
        db.create_all()

    # Store the task queue and db_uri in app config for access in blueprints
    app.config['TASK_QUEUE'] = task_queue
    app.config['RESULTS_QUEUE'] = results_queue # Store results queue in config
    app.config['DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI']

    # Import and register blueprints
    from app.auth import auth_bp
    from app.files import files_bp
    from app.init_register import setup_bp
    from app.workers import workers_bp # Import the new workers blueprint

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(files_bp) # Register the new files blueprint
    app.register_blueprint(setup_bp)
    app.register_blueprint(workers_bp) # Register the new workers blueprint

    @app.route('/')
    def initial_redirect():
        # If an admin user exists, redirect to the login page.
        # Otherwise, redirect to the setup page.
        if User.query.filter_by(is_admin=True).first():
            return redirect(url_for('auth.login'))
        else:
            return redirect(url_for('setup.setup_admin'))

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
                            file_record.filepath = new_file_path # Update filepath in DB
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
                except (ValueError, EOFError) as e:
                    logger.error(f"Error in results processing thread during shutdown: {e}", exc_info=True)
                    break # Exit loop to allow thread to terminate
                except Exception as e:
                    logger.error(f"Error in results processing thread: {e}", exc_info=True)

    results_thread = Thread(target=process_results_from_queue, args=(app.app_context(),))
    results_thread.daemon = True
    results_thread.start()
    app.config['RESULTS_THREAD'] = results_thread # Store thread for potential management

    



def shutdown_workers(app): # Accept app as argument
    """Sends stop signals to workers and joins them."""
    logger.info("Shutting down worker processes...")
    for _ in worker_processes:
        task_queue.put((None, None, None)) # Send sentinel value to stop each worker (now expects 3 args)
    
    # Send sentinel to results processing thread
    results_queue.put((None, None, None, None, None, None)) # Now expects 6 args

    

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
