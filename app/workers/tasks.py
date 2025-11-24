import os
import logging
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.workers.handlers import FileProcessingTask
from app.mq import mq
from app.config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_db_session(db_uri: str) -> Session:
    """Cria e retorna uma nova sessão de banco de dados SQLAlchemy."""
    engine = create_engine(db_uri)
    Session = sessionmaker(bind=engine)
    return Session()

def process_file_task(file_id: int, file_path: str, current_retries: int, db_uri: str, session: Session):
    """
    Ponto de entrada para processar um arquivo.
    Instancia e executa a tarefa de processamento de arquivo.
    """
    task = FileProcessingTask(
        file_id=file_id,
        file_path=file_path,
        retries=current_retries,
        session=session
    )
    task.run()

def worker_main(db_uri: str):
    """
    O loop principal para um worker.
    Escuta por tarefas e as executa.
    """
    logger.info(f"Worker started. Listening for tasks...")

    def callback(ch, method, properties, body):
        worker_session = None
        try:
            message = json.loads(body)
            file_id = message['file_id']
            file_path = message['filepath']
            current_retries = message['retries']
            logger.info(f"Worker received task: File ID {file_id}")

            worker_session = _get_db_session(db_uri)
            process_file_task(file_id, file_path, current_retries, db_uri, session=worker_session)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error(f"Worker encountered a critical error: {e}", exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        finally:
            if worker_session and worker_session.is_active:
                worker_session.close()

    mq.consume_tasks(callback)