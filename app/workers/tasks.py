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

_engine = None
_SessionFactory = None

def _get_db_session(db_uri: str) -> Session:
    """Retorna uma sessão de banco de dados, criando o engine apenas uma vez."""
    global _engine, _SessionFactory
    if _engine is None:
        _engine = create_engine(db_uri, pool_size=1, max_overflow=0, pool_recycle=1800)
        _SessionFactory = sessionmaker(bind=_engine)
    return _SessionFactory()

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
    worker_mq.connect() # No longer raises if connection fails, sets use_local_fallback instead

    try:
        while True:
            method_frame = None
            body = None

            # 1. Tenta pegar da fila LOCAL primeiro
            from app.mq import local_task_queue
            if not local_task_queue.empty():
                try:
                    body = local_task_queue.get_nowait()
                    logger.info(f"Worker {os.getpid()} picking task from LOCAL queue.")
                except Exception:
                    pass

            # 2. Se não tinha na local e o RabbitMQ estiver disponível, tenta dele
            if not body and not worker_mq.use_local_fallback:
                try:
                    method_frame, header_frame, body = worker_mq.channel.basic_get(
                        queue=worker_mq.task_queue_name, 
                        auto_ack=False
                    )
                except Exception:
                    worker_mq.use_local_fallback = True

            if body:
                worker_session = None
                try:
                    message = json.loads(body)
                    file_id = message['file_id']
                    file_path = message['filepath']
                    logger.info(f"Worker {os.getpid()} received task: File ID {file_id}")

                    worker_session = _get_db_session(db_uri)
                    process_file_task(file_id, file_path, db_uri, session=worker_session)
                    
                    # Acknowledge the message after successful processing
                    if method_frame:
                        worker_mq.channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    logger.error(f"Worker {os.getpid()} encountered an error processing task: {e}", exc_info=True)
                    if method_frame:
                        worker_mq.channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=False)
                finally:
                    if worker_session:
                        worker_session.close()
            else:
                # No tasks found in either queue, exit worker
                logger.info(f"Worker {os.getpid()} found no more tasks. Shutting down.")
                break
    except Exception as e:
        logger.error(f"Worker {os.getpid()} critical error: {e}")
    finally:
        worker_mq.close()