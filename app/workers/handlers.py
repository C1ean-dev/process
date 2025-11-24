import os
import logging
import json
import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
from multiprocessing import Queue

from app.models import File, record_metric
from app.config import Config
from app.workers.pdf_processing.extraction import extract_text_from_pdf, extract_data_from_text
from app.workers.duplicate_checker.tasks import process_file_for_duplicates
from app.mq import mq

logger = logging.getLogger(__name__)

class FileProcessingTask:
    """
    Encapsula a lógica de orquestração para processar um único arquivo.
    """

    def __init__(self, file_id: int, file_path: str, retries: int, session: Session):
        self.file_id = file_id
        self.original_filepath = file_path
        self.current_filepath = file_path
        self.retries = retries
        self.session = session
        self.status = 'pending'
        self.processed_data = ""
        self.structured_data = {}

    def run(self):
        """Executa o fluxo de processamento do arquivo."""
        try:
            logger.info(f"Worker {os.getpid()} starting task for file ID {self.file_id} (Attempt {self.retries + 1})")
            self._update_db_status('processing')

            if self._is_duplicate():
                self._handle_duplicate()
                return

            self._extract_data()
            self._upload_to_r2()

            self.status = 'completed'

        except FileNotFoundError as e:
            self._handle_error(f"File not found: {e}")
        except ValueError as e: # Para tipos de arquivo não suportados
            self._handle_error(f"Unsupported file type: {e}")
        except Exception as e:
            self._handle_error(f"An unexpected error occurred: {e}")
        finally:
            self._finalize_task()

    def _is_duplicate(self):
        return process_file_for_duplicates(self.file_id, self.current_filepath, self.session, File)

    def _handle_duplicate(self):
        logger.info(f"File {self.file_id} is a duplicate. Halting processing.")
        self.status = 'duplicate'
        self.processed_data = "Duplicate file detected."
        self._update_db_status('duplicate', processed_data=self.processed_data)

    def _extract_data(self):
        file_extension = os.path.splitext(self.current_filepath)[1].lower()
        if file_extension != '.pdf':
            raise ValueError(f"Unsupported file type: {file_extension}")
        self.processed_data = extract_text_from_pdf(self.current_filepath)
        if self.processed_data and self.processed_data.strip():
            self.structured_data = extract_data_from_text(self.processed_data)
        else:
            logger.warning(f"Extraction returned empty text for {self.file_id}. No structured data.")

    def _upload_to_r2(self):
        if Config.R2_FEATURE_FLAG == 'True':
            filename = os.path.basename(self.original_filepath)
            r2_url = self._get_r2_uploader().upload(self.current_filepath, filename)

            if r2_url:
                logger.info(f"File {self.file_id} successfully uploaded to R2.")
                self.current_filepath = r2_url
                try:
                    os.remove(self.original_filepath)
                    logger.info(f"Removed local file: {self.original_filepath}")
                except OSError as e:
                    logger.error(f"Error removing local file {self.original_filepath}: {e}")
            else:
                self.retries += 1
                self.processed_data += "\nWarning: Failed to upload to Cloudflare R2."
                raise IOError("Failed to upload file to R2.")
        else:
            logger.info(f"R2_FEATURE_FLAG is disabled. Moving file to completed folder for file ID {self.file_id}.")
            os.makedirs(Config.COMPLETED_FOLDER, exist_ok=True)
            new_path = os.path.join(Config.COMPLETED_FOLDER, os.path.basename(self.original_filepath))
            try:
                os.rename(self.original_filepath, new_path)
                self.current_filepath = new_path
                logger.info(f"Moved file to {new_path}")
            except OSError as e:
                logger.error(f"Error moving file {self.original_filepath} to {new_path}: {e}")
                raise

    def _handle_error(self, error_message):
        logger.error(f"Error processing file ID {self.file_id}: {error_message}", exc_info=True)
        self.status = 'failed'
        self.retries += 1
        self.processed_data = error_message
        self._update_db_status('failed', processed_data=error_message)

    def _finalize_task(self):
        self._update_db_status(
            status=self.status,
            file_path=self.current_filepath,
            processed_data=self.processed_data,
            structured_data=self.structured_data
        )
        if self.status == 'completed' and self.structured_data:
            equipamentos = self.structured_data.get('equipamentos', [])
            record_metric('equipment_count', len(equipamentos), {'file_id': self.file_id}, self.session)
            imei_numbers = self.structured_data.get('imei_numbers', [])
            record_metric('imei_count', len(imei_numbers), {'file_id': self.file_id}, self.session)
            patrimonio_numbers = self.structured_data.get('patrimonio_numbers', [])
            record_metric('patrimonio_count', len(patrimonio_numbers), {'file_id': self.file_id}, self.session)
        mq.publish_result({
            'file_id': self.file_id,
            'status': self.status,
            'processed_data': self.processed_data,
            'retries': self.retries,
            'filepath': self.current_filepath,
            'structured_data': self.structured_data
        })
        logger.info(f"Worker {os.getpid()} finished task for file ID {self.file_id}. Final status: {self.status}")

    def _update_db_status(self, status, file_path=None, processed_data=None, structured_data=None):
        try:
            file_record = self.session.get(File, self.file_id)
            if file_record:
                file_record.status = status
                file_record.retries = self.retries
                if file_path: file_record.filepath = file_path
                if processed_data: file_record.processed_data = processed_data.strip()
                if structured_data:
                    file_record.nome = structured_data.get('nome')
                    file_record.matricula = structured_data.get('matricula')
                    file_record.funcao = structured_data.get('funcao')
                    file_record.empregador = structured_data.get('empregador')
                    file_record.rg = structured_data.get('rg')
                    file_record.cpf = structured_data.get('cpf')
                    file_record.equipamentos = json.dumps(structured_data.get('equipamentos')) if structured_data.get('equipamentos') else None
                    file_record.data_documento = structured_data.get('data')
                    file_record.imei_numbers = json.dumps(structured_data.get('imei_numbers')) if structured_data.get('imei_numbers') else None
                    file_record.patrimonio_numbers = json.dumps(structured_data.get('patrimonio_numbers')) if structured_data.get('patrimonio_numbers') else None
                self.session.commit()
                logger.info(f"DB status for file ID {self.file_id} updated to '{status}'.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"DB update failed for file ID {self.file_id}: {e}", exc_info=True)

    def _get_r2_uploader(self):
        return R2Uploader()

class R2Uploader:
    """Handles file uploads to Cloudflare R2."""
    def __init__(self):
        self.s3_client = self._get_client()

    def _get_client(self):
        if not all([Config.CLOUDFLARE_ACCOUNT_ID, Config.CLOUDFLARE_R2_ACCESS_KEY_ID,
                    Config.CLOUDFLARE_R2_SECRET_ACCESS_KEY, Config.CLOUDFLARE_R2_BUCKET_NAME]):
            logger.error("R2 credentials not fully configured.")
            return None
        try:
            return boto3.client(
                service_name='s3',
                endpoint_url=Config.CLOUDFLARE_R2_ENDPOINT_URL,
                aws_access_key_id=Config.CLOUDFLARE_R2_ACCESS_KEY_ID,
                aws_secret_access_key=Config.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
                region_name='auto'
            )
        except Exception as e:
            logger.error(f"Error initializing R2 client: {e}")
            return None

    def upload(self, local_file_path, object_name):
        if not self.s3_client:
            return None
        try:
            self.s3_client.upload_file(local_file_path, Config.CLOUDFLARE_R2_BUCKET_NAME, object_name)
            # Retornar a URL pública não assinada é geralmente mais útil para armazenamento no DB
            public_url = f"{Config.CLOUDFLARE_R2_ENDPOINT_URL}/{object_name}"
            logger.info(f"File uploaded to R2. Public URL: {public_url}")
            return public_url
        except ClientError as e:
            logger.error(f"Failed to upload {local_file_path} to R2: {e}")
            return None
