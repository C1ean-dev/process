import os
import logging
import json
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.workers.handlers import FileProcessingTask
from app.mq import mq, MessageQueue
from app.config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_db_session(db_uri: str) -> Session:
    """Cria e retorna uma nova sessão de banco de dados SQLAlchemy."""
    engine = create_engine(db_uri)
    Session = sessionmaker(bind=engine)
    return Session()

def process_file_task(file_id: int, file_path: str, db_uri: str, session: Session):
    """
    Ponto de entrada para processar um arquivo.
    Instancia e executa a tarefa de processamento de arquivo.
    """
    task = FileProcessingTask(
        file_id=file_id,
        file_path=file_path,
        session=session
    )
    task.run()

def worker_main(db_uri: str):
    """
    O loop principal para um worker.
    Processa tarefas até que a fila esteja vazia e então termina.
    """
    logger.info(f"Worker {os.getpid()} started. Checking for tasks...")
    
    # Use a local MessageQueue instance for each worker process
    worker_mq = MessageQueue()
    try:
        worker_mq.connect()
    except Exception as e:
        logger.error(f"Worker {os.getpid()} failed to connect to MQ: {e}")
        return

    try:
        while True:
            # Try to get a single message from the queue
            method_frame, header_frame, body = worker_mq.channel.basic_get(
                queue=worker_mq.task_queue_name, 
                auto_ack=False
            )
            
            if method_frame:
                worker_session = None
                try:
                    message = json.loads(body)
                    file_id = message['file_id']
                    file_path = message['filepath']
                    logger.info(f"Worker {os.getpid()} received task: File ID {file_id}")

                    worker_session = _get_db_session(db_uri)
                    process_file_task(file_id, file_path, db_uri, session=worker_session)
                    
                    # Acknowledge the message after successful processing
                    worker_mq.channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    logger.error(f"Worker {os.getpid()} encountered an error processing task: {e}", exc_info=True)
                    # Requeue=False to avoid infinite loops on bad tasks
                    worker_mq.channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=False)
                finally:
                    if worker_session:
                        worker_session.close()
            else:
                # No tasks found, exit worker to free resources
                logger.info(f"Worker {os.getpid()} found no more tasks. Shutting down.")
                break
    except Exception as e:
        logger.error(f"Worker {os.getpid()} critical error: {e}")
    finally:
        worker_mq.close()