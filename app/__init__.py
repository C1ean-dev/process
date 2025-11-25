import json
import os
import logging

from flask import Flask, redirect, url_for, flash, render_template, request
from .config import Config # Changed to relative import
from .models import db, User, File # Import File model
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user
from .mq import mq # Import message queue
from .workers.tasks import worker_main # Import worker_main
import atexit # For graceful shutdown
import threading # Import threading for Event
import json # Import json for structured data serialization
from multiprocessing import Process

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


# Global message queue


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

    # Store the message queue and db_uri in app config for access in blueprints
    app.config['MQ'] = mq
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
    """Starts the worker processes and results consumer thread."""
    worker_processes = []
    # Start worker processes
    for _ in range(Config.NUM_WORKERS):
        worker_process = Process(target=worker_main, args=(app.config['DATABASE_URI'],))
        worker_process.start()
        worker_processes.append(worker_process)
        logger.info(f"Worker process {worker_process.pid} started.")
    app.config['WORKER_PROCESSES'] = worker_processes

    # Start a background thread to process results from workers
    from threading import Thread
    def process_results_from_queue(app_context):
        def callback(ch, method, properties, body):
            with app_context:
                try:
                    message = json.loads(body)
                    file_id = message['file_id']
                    new_status = message['status']
                    processed_data = message['processed_data']
                    new_file_path = message['filepath']
                    extracted_structured_data = message['structured_data']

                    # Import File model here to ensure it's available in the thread's context
                    from .models import File

                    file_record = db.session.query(File).get(file_id)
                    if file_record:
                        file_record.processed_data = processed_data

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

                        file_record.status = new_status
                        file_record.filepath = new_file_path
                        try:
                            db.session.commit()
                            logger.info(f"Main app updated file {file_id} to status '{new_status}' and filepath '{new_file_path}'.")
                        except Exception as commit_e:
                            db.session.rollback()
                            logger.error(f"Error committing file status update for {file_id}: {commit_e}", exc_info=True)
                    else:
                        logger.warning(f"Main app could not find file {file_id} to update status.")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logger.error(f"Error in results processing: {e}", exc_info=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        mq.consume_results(callback)

    results_thread = Thread(target=process_results_from_queue, args=(app.app_context(),))
    results_thread.daemon = True
    results_thread.start()
    app.config['RESULTS_THREAD'] = results_thread # Store thread for potential management

    



def shutdown_workers(app): # Accept app as argument
    """Shuts down the worker processes and results processing thread."""
    logger.info("Shutting down worker processes...")

    # Terminate worker processes
    if 'WORKER_PROCESSES' in app.config:
        for worker_process in app.config['WORKER_PROCESSES']:
            if worker_process.is_alive():
                worker_process.terminate()
                worker_process.join(timeout=5)
                if worker_process.is_alive():
                    logger.warning(f"Worker process {worker_process.pid} did not terminate gracefully.")
        logger.info("Worker processes shut down.")

    logger.info("Shutting down results processing thread...")

    # Wait for results thread to finish
    if 'RESULTS_THREAD' in app.config and app.config['RESULTS_THREAD'].is_alive(): # Use app.config
        app.config['RESULTS_THREAD'].join(timeout=5) # Use app.config
        if app.config['RESULTS_THREAD'].is_alive():
            logger.warning("Results processing thread did not terminate gracefully.")

    mq.close()
    logger.info("Results thread and message queue shut down.")
