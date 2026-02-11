import os
from dotenv import load_dotenv 
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__)) 
    PROJECT_ROOT = os.path.join(BASE_DIR, os.pardir)
    INSTANCE_FOLDER = os.path.join(PROJECT_ROOT)
    os.makedirs(INSTANCE_FOLDER, exist_ok=True)

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 2,
        "max_overflow": 3,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024
    MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB
    MAX_PDF_PAGES = int(os.environ.get('MAX_PDF_PAGES'))
    FOLDER_MONITOR_INTERVAL_SECONDS = 60
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    #COMPLETED_FOLDER = os.path.join(os.getcwd(), 'completed')

    # Feature Flags
    R2_FEATURE_FLAG = 'True'
    ENABLE_OCR = 'True'

    # External tool paths (adjust as needed for your environment)
    TESSERACT_CMD = os.path.join(PROJECT_ROOT, 'libs', 'Tesseract-OCR', 'tesseract.exe')
    POPPLER_PATH = os.path.join(PROJECT_ROOT, 'libs', 'poppler-25.11.0', 'Library', 'bin')

    # Cloudflare R2 (S3-compatible) Configuration
    CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CLOUDFLARE_R2_ACCESS_KEY_ID = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID')
    CLOUDFLARE_R2_SECRET_ACCESS_KEY = os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
    CLOUDFLARE_R2_BUCKET_NAME = os.environ.get('CLOUDFLARE_R2_BUCKET_NAME')
    CLOUDFLARE_R2_ENDPOINT_URL = os.environ.get('CLOUDFLARE_R2_ENDPOINT_URL')

    # CloudAMQP Configuration
    CLOUDAMQP_URL = os.environ.get('CLOUDAMQP_URL')
    FLASK_ENV = os.environ.get('FLASK_ENV')

    # Mail Configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'erick13r13@gmail.com'
    MAIL_PASSWORD = 'zddn ldlv jwsc iwzj'
    MAIL_DEFAULT_SENDER = 'erick13r13@gmail.com'

    
