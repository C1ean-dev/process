import pika
import json
import logging
from app.config import Config

logger = logging.getLogger(__name__)

class MessageQueue:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.task_queue_name = 'file_processing_queue'
        self.results_queue_name = 'file_processing_results'

    def connect(self):
        try:
            parameters = pika.URLParameters(Config.CLOUDAMQP_URL)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.channel.queue_declare(queue=self.task_queue_name, durable=True)
            self.channel.queue_declare(queue=self.results_queue_name, durable=True)
            logger.info("Connected to CloudAMQP")
        except Exception as e:
            logger.error(f"Failed to connect to CloudAMQP: {e}")
            raise

    def publish_task(self, message):
        if not self.channel:
            self.connect()
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.task_queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                )
            )
            logger.info(f"Published task message to queue: {message}")
        except Exception as e:
            logger.error(f"Failed to publish task message: {e}")
            raise

    def publish_result(self, message):
        if not self.channel:
            self.connect()
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.results_queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                )
            )
            logger.info(f"Published result message to queue: {message}")
        except Exception as e:
            logger.error(f"Failed to publish result message: {e}")
            raise

    def consume_tasks(self, callback):
        if not self.channel:
            self.connect()
        try:
            self.channel.basic_consume(queue=self.task_queue_name, on_message_callback=callback, auto_ack=False)
            logger.info("Starting to consume task messages")
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"Failed to consume task messages: {e}")
            raise

    def consume_results(self, callback):
        if not self.channel:
            self.connect()
        try:
            self.channel.basic_consume(queue=self.results_queue_name, on_message_callback=callback, auto_ack=False)
            logger.info("Starting to consume result messages")
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"Failed to consume result messages: {e}")
            raise

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("Closed CloudAMQP connection")

# Global instance
mq = MessageQueue()