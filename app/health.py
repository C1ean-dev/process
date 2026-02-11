import os
import pika
import boto3
from sqlalchemy import text
from app.models import db
from app.config import Config
import logging

logger = logging.getLogger(__name__)

def check_database():
    try:
        db.session.execute(text("SELECT 1"))
        return True, "Operacional"
    except Exception as e:
        logger.error(f"Erro no Banco de Dados: {e}")
        return False, f"Indisponível: {str(e)}"
    finally:
        db.session.remove()

def check_mq():
    if not Config.CLOUDAMQP_URL:
        return False, "Configuração CLOUDAMQP_URL ausente"
    try:
        parameters = pika.URLParameters(Config.CLOUDAMQP_URL)
        parameters.connection_attempts = 1
        parameters.retry_delay = 1
        connection = pika.BlockingConnection(parameters)
        if connection.is_open:
            connection.close()
            return True, "Operacional"
        return False, "Conexão falhou"
    except Exception as e:
        logger.error(f"Erro no CloudAMQP: {e}")
        return False, f"Indisponível: {str(e)}"

def check_storage():
    if Config.R2_FEATURE_FLAG != 'True':
        return True, "Desativado (Local Storage)"
    
    if not all([Config.CLOUDFLARE_R2_ENDPOINT_URL, Config.CLOUDFLARE_R2_ACCESS_KEY_ID, Config.CLOUDFLARE_R2_SECRET_ACCESS_KEY]):
        return False, "Configurações de R2 incompletas no .env"

    try:
        from botocore.config import Config as BotoConfig
        s3 = boto3.client(
            's3',
            endpoint_url=Config.CLOUDFLARE_R2_ENDPOINT_URL,
            aws_access_key_id=Config.CLOUDFLARE_R2_ACCESS_KEY_ID,
            aws_secret_access_key=Config.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
            region_name='auto',
            config=BotoConfig(signature_version='s3v4')
        )
        s3.head_bucket(Bucket=Config.CLOUDFLARE_R2_BUCKET_NAME)
        return True, "Operacional"
    except Exception as e:
        error_msg = str(e)

        if "403" in error_msg or "404" in error_msg:
             return True, "Operacional (Conectado)"
        
        logger.error(f"Erro no Cloudflare R2: {e}")
        return False, f"Erro de Conexão: {error_msg}"

def check_tesseract():
    if os.path.exists(Config.TESSERACT_CMD):
        return True, "Operacional"
    return False, f"Executável não encontrado em {Config.TESSERACT_CMD}"

def check_poppler():
    if os.path.exists(Config.POPPLER_PATH):
        return True, "Operacional"
    return False, f"Binários não encontrados em {Config.POPPLER_PATH}"

def get_health_status():
    services = {
        "database": {
            "name": "Banco de Dados",
            "status": None,
            "message": None,
            "impact": "Impossibilita o login, cadastro e visualização de arquivos."
        },
        "mq": {
            "name": "Fila de Mensagens (Hybrid)",
            "status": None,
            "message": None,
            "impact": "Se o CloudAMQP falhar, o sistema usará automaticamente uma fila local em memória. O processamento continuará, mas os dados não serão persistidos se o servidor reiniciar."
        },
        "storage": {
            "name": "Armazenamento (Cloudflare R2)",
            "status": None,
            "message": None,
            "impact": "Impossibilita o upload e download de arquivos."
        },
        "tesseract": {
            "name": "OCR (Tesseract)",
            "status": None,
            "message": None,
            "impact": "O texto dos documentos não será extraído corretamente."
        },
        "poppler": {
            "name": "PDF Processing (Poppler)",
            "status": None,
            "message": None,
            "impact": "Documentos PDF não poderão ser convertidos em imagens para processamento."
        }
    }

    services["database"]["status"], services["database"]["message"] = check_database()
    
    mq_ok, mq_msg = check_mq()
    if not mq_ok:
        services["mq"]["status"] = True # Marcamos como True (amarelo/operacional) pois o fallback local está ativo
        services["mq"]["message"] = f"CloudAMQP Indisponível. Usando Fila Local de Emergência. ({mq_msg})"
        services["mq"]["is_warning"] = True # Flag para o frontend se necessário
    else:
        services["mq"]["status"] = True
        services["mq"]["message"] = "CloudAMQP Operacional"

    services["storage"]["status"], services["storage"]["message"] = check_storage()
    services["tesseract"]["status"], services["tesseract"]["message"] = check_tesseract()
    services["poppler"]["status"], services["poppler"]["message"] = check_poppler()

    overall_status = all(s["status"] for s in services.values())
    
    return {
        "status": "healthy" if overall_status else "degraded",
        "services": services
    }
