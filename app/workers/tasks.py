import os
import logging
from multiprocessing import Process, Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.workers.handlers import FileProcessingTask

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_db_session(db_uri: str) -> Session:
    """Cria e retorna uma nova sessão de banco de dados SQLAlchemy."""
    engine = create_engine(db_uri)
    Session = sessionmaker(bind=engine)
    return Session()

def process_file_task(file_id: int, file_path: str, current_retries: int, results_queue: Queue, db_uri: str, session: Session):
    """
    Ponto de entrada para processar um arquivo.
    Instancia e executa a tarefa de processamento de arquivo.
    """
    task = FileProcessingTask(
        file_id=file_id,
        file_path=file_path,
        retries=current_retries,
        results_q=results_queue,
        session=session
    )
    task.run()

def worker_main(task_queue: Queue, results_queue: Queue, db_uri: str):
    """
    O loop principal para um processo worker.
    Escuta por tarefas e as executa.
    """
    logger.info(f"Worker process started. PID: {os.getpid()}. Listening for tasks...")
    
    while True:
        worker_session = None
        try:
            task_data = task_queue.get()
            if task_data is None:
                logger.info(f"Worker {os.getpid()} received stop signal. Exiting.")
                break

            file_id, file_path, current_retries = task_data
            logger.info(f"Worker {os.getpid()} received task: File ID {file_id}")
            
            worker_session = _get_db_session(db_uri)
            process_file_task(file_id, file_path, current_retries, results_queue, db_uri, session=worker_session)

        except (KeyboardInterrupt, SystemExit):
            logger.info(f"Worker {os.getpid()} shutting down.")
            break
        except Exception as e:
            logger.error(f"Worker {os.getpid()} encountered a critical error: {e}", exc_info=True)
        finally:
            if worker_session and worker_session.is_active:
                worker_session.close()