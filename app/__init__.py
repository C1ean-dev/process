import json
import os
import logging
import multiprocessing
import time
from threading import Thread, Event

from flask import Flask, redirect, url_for, flash, render_template, request
from .config import Config # Changed to relative import
from .models import db, User, File # Import File model
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user
from .mq import mq # Import message queue
from .workers.tasks import worker_main # Import worker_main
import atexit # For graceful shutdown
from multiprocessing import Process

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Event to signal background threads to stop
shutdown_event = Event()

def from_json(value):
    """Jinja2 filter to parse JSON strings."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value # Return original value if not valid JSON


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
    """Starts the dynamic worker manager and results consumer thread."""
    db_uri = app.config['DATABASE_URI']
    app_context = app.app_context()
    
    # 1. Start a background thread to process results from workers
    def process_results_from_queue(ctx):
        from .mq import MessageQueue
        thread_mq = MessageQueue()
        logger.info("Results processing thread started.")
        def callback(ch, method, properties, body):
            with ctx:
                try:
                    message = json.loads(body)
                    file_id = message['file_id']
                    new_status = message['status']
                    processed_data = message['processed_data']
                    new_file_path = message['filepath']
                    extracted_structured_data = message['structured_data']

                    from .models import File
                    file_record = db.session.query(File).get(file_id)
                    if file_record:
                        file_record.processed_data = processed_data
                        file_record.nome = extracted_structured_data.get('nome')
                        file_record.matricula = extracted_structured_data.get('matricula')
                        file_record.funcao = extracted_structured_data.get('funcao')
                        file_record.empregador = extracted_structured_data.get('empregador')
                        file_record.rg = extracted_structured_data.get('rg')
                        file_record.cpf = extracted_structured_data.get('cpf')
                        file_record.data_documento = extracted_structured_data.get('data')

                        if 'equipamentos' in extracted_structured_data and extracted_structured_data['equipamentos'] is not None:
                            file_record.equipamentos = json.dumps(extracted_structured_data['equipamentos'])
                        else:
                            file_record.equipamentos = None

                        imei_list = extracted_structured_data.get('imei_numbers')
                        file_record.imei_numbers = json.dumps(imei_list) if imei_list is not None else None

                        patrimonio_list = extracted_structured_data.get('patrimonio_numbers')
                        file_record.patrimonio_numbers = json.dumps(patrimonio_list) if patrimonio_list is not None else None

                        file_record.status = new_status
                        file_record.filepath = new_file_path
                        db.session.commit()
                        logger.info(f"Main app updated file {file_id} to status '{new_status}'.")
                    
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logger.error(f"Error in results processing: {e}", exc_info=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        try:
            thread_mq.consume_results(callback)
        except Exception as e:
            logger.error(f"Results thread encountered an error: {e}")
        finally:
            thread_mq.close()

    results_thread = Thread(target=process_results_from_queue, args=(app_context,))
    results_thread.daemon = True
    results_thread.start()
    app.config['RESULTS_THREAD'] = results_thread

    # 2. Start the Dynamic Worker Manager
    def worker_manager():
        from .mq import MessageQueue
        manager_mq = MessageQueue()
        worker_processes = []
        max_workers = max(1, multiprocessing.cpu_count() - 1)
        logger.info(f"Worker Manager started. Max workers: {max_workers}")
        
        try:
            while not shutdown_event.is_set():
                # Clean up finished processes
                worker_processes = [p for p in worker_processes if p.is_alive()]
                
                # Check queue size
                try:
                    q_size = manager_mq.get_queue_size()
                except Exception as e:
                    logger.error(f"Manager failed to get queue size: {e}")
                    q_size = 0
                    
                running = len(worker_processes)
                
                if q_size > 0 and running < max_workers:
                    # Spawn workers based on demand, up to max_workers
                    needed = min(q_size, max_workers - running)
                    for _ in range(needed):
                        p = Process(target=worker_main, args=(db_uri,))
                        p.start()
                        worker_processes.append(p)
                        logger.info(f"Spawned new worker process {p.pid}. Running: {len(worker_processes)}, Queue: {q_size}")
                
                # Check every 5 seconds
                time.sleep(5)
        finally:
            logger.info("Worker Manager shutting down. Waiting for workers...")
            for p in worker_processes:
                p.join(timeout=10)
                if p.is_alive():
                    p.terminate()
            manager_mq.close()

    manager_thread = Thread(target=worker_manager)
    manager_thread.daemon = True
    manager_thread.start()
    app.config['MANAGER_THREAD'] = manager_thread

def shutdown_workers(app):
    """Signals all background tasks to stop."""
    logger.info("Shutting down workers and manager...")
    shutdown_event.set()
    
    if 'MANAGER_THREAD' in app.config:
        app.config['MANAGER_THREAD'].join(timeout=15)
        
    mq.close()
    logger.info("Shutdown complete.")

