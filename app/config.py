import os
from dotenv import load_dotenv 
load_dotenv()

class Config:
    NUM_WORKERS = '12'
    SECRET_KEY = os.environ.get('SECRET_KEY')
    BASE_DIR = os.path.abspath(os.path.dirname(__file__)) 
    PROJECT_ROOT = os.path.join(BASE_DIR, os.pardir)
    INSTANCE_FOLDER = os.path.join(PROJECT_ROOT, 'instance')
    os.makedirs(INSTANCE_FOLDER, exist_ok=True)

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(INSTANCE_FOLDER, "site.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    COMPLETED_FOLDER = os.path.join(os.getcwd(), 'completed')
     

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024 
    MAX_RETRIES = 3 
    FOLDER_MONITOR_INTERVAL_SECONDS = 60 

    # Feature Flags
    R2_FEATURE_FLAG = 'False'
    ENABLE_PDF_COMPRESSION = 'False'
    ENABLE_OCR = 'True'

    # External tool paths (adjust as needed for your environment)
    TESSERACT_CMD = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
    POPPLER_PATH = 'C:\\poppler\\Library\\bin'
    GHOSTSCRIPT_EXEC = 'C:\\Program Files\\gs\\gs10.05.1\\bin\\gswin64c.exe'

    # Cloudflare R2 (S3-compatible) Configuration
    CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CLOUDFLARE_R2_ACCESS_KEY_ID = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID')
    CLOUDFLARE_R2_SECRET_ACCESS_KEY = os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
    CLOUDFLARE_R2_BUCKET_NAME = os.environ.get('CLOUDFLARE_R2_BUCKET_NAME')
    CLOUDFLARE_R2_ENDPOINT_URL = os.environ.get('CLOUDFLARE_R2_ENDPOINT_URL')
