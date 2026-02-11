import pika
import json
import logging
import multiprocessing
from app.config import Config

logger = logging.getLogger(__name__)

# Fila local para fallback caso o RabbitMQ falhe
local_task_queue = multiprocessing.Queue()
local_results_queue = multiprocessing.Queue()

class MessageQueue:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.task_queue_name = 'file_processing_queue'
        self.results_queue_name = 'file_processing_results'
        self.use_local_fallback = False

    def connect(self):
        try:
            parameters = pika.URLParameters(Config.CLOUDAMQP_URL)
            # Timeout curto para detecção rápida de falha
            parameters.connection_attempts = 1
            parameters.retry_delay = 1
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.task_queue_name, durable=True)
            self.channel.queue_declare(queue=self.results_queue_name, durable=True)
            logger.info("Connected to CloudAMQP")
            self.use_local_fallback = False
            return True
        except Exception as e:
            logger.error(f"Failed to connect to CloudAMQP, using local fallback: {e}")
            self.use_local_fallback = True
            return False

    def publish_task(self, message):
        # Tenta conectar se não houver conexão ativa
        if not self.connection or self.connection.is_closed:
            self.connect()

        if self.use_local_fallback:
            logger.info(f"Publishing task to LOCAL queue: {message}")
            local_task_queue.put(json.dumps(message))
            return

        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.task_queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"Published task to CloudAMQP: {message}")
        except Exception as e:
            logger.warning(f"Failed to publish to CloudAMQP, falling back to local: {e}")
            self.use_local_fallback = True
            local_task_queue.put(json.dumps(message))

    def publish_result(self, message):
        if not self.connection or self.connection.is_closed:
            # Não tentamos reconectar aqui para evitar delay no worker, 
            # apenas verificamos o estado
            pass

        if self.use_local_fallback or not self.connection or self.connection.is_closed:
            logger.info(f"Publishing result to LOCAL queue: {message}")
            local_results_queue.put(json.dumps(message))
            return

        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.results_queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
        except Exception as e:
            logger.error(f"Failed to publish result to CloudAMQP: {e}")
            local_results_queue.put(json.dumps(message))

    def get_queue_size(self):
        """Returns the combined size of RabbitMQ and local queue."""
        local_size = local_task_queue.qsize()
        
        if not self.channel or self.channel.is_closed:
            if not self.connect():
                return local_size
        
        try:
            res = self.channel.queue_declare(queue=self.task_queue_name, durable=True, passive=True)
            return res.method.message_count + local_size
        except Exception:
            return local_size

    def consume_tasks(self, callback):
        # Primeiro processa tudo o que estiver na fila local
        while not local_task_queue.empty():
            try:
                body = local_task_queue.get_nowait()
                # Mock do canal e método para o callback
                class MockChannel:
                    def basic_ack(self, delivery_tag): pass
                callback(MockChannel(), None, None, body)
            except Exception:
                break

        # Depois tenta consumir do RabbitMQ
        if not self.channel:
            self.connect()
        
        if not self.use_local_fallback:
            try:
                self.channel.basic_consume(queue=self.task_queue_name, on_message_callback=callback, auto_ack=False)
                self.channel.start_consuming()
            except Exception as e:
                logger.error(f"Error consuming from RabbitMQ: {e}")
                self.use_local_fallback = True

    def consume_results(self, callback):
        # Esta função agora é chamada em uma thread, precisamos que ela cheque ambos
        while True:
            # 1. Checa fila local
            while not local_results_queue.empty():
                try:
                    body = local_results_queue.get_nowait()
                    class MockChannel:
                        def basic_ack(self, delivery_tag): pass
                    callback(MockChannel(), type('obj', (object,), {'delivery_tag': 0}), None, body)
                except Exception:
                    break
            
            # 2. Tenta CloudAMQP
            if not self.connection or self.connection.is_closed:
                self.connect()
            
            if not self.use_local_fallback:
                try:
                    # Usamos consume com timeout para não travar a thread e podermos checar a fila local de novo
                    for method_frame, properties, body in self.channel.consume(self.results_queue_name, inactivity_timeout=1):
                        if body:
                            callback(self.channel, method_frame, properties, body)
                        break # Volta para checar a fila local
                except Exception:
                    self.use_local_fallback = True
            
            import time
            time.sleep(1)

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()

# Instância global
mq = MessageQueue()