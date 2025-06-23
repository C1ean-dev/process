import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_key_that_should_be_changed'
    # Ensure the database URI uses an absolute path for consistency across processes
    # The 'instance' folder is typically used by Flask for instance-specific files.
    # We ensure it's created relative to the project root.
    BASE_DIR = os.path.abspath(os.path.dirname(__file__)) # This gets 'app' directory
    PROJECT_ROOT = os.path.join(BASE_DIR, os.pardir) # This gets 'projeto/process'
    INSTANCE_FOLDER = os.path.join(PROJECT_ROOT, 'instance')
    os.makedirs(INSTANCE_FOLDER, exist_ok=True) # Ensure instance folder exists

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(INSTANCE_FOLDER, "site.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    PENDING_FOLDER = os.path.join(os.getcwd(), 'aguardando_processo') 
    PROCESSING_FOLDER = os.path.join(os.getcwd(), 'processando') 
    COMPLETED_FOLDER = os.path.join(os.getcwd(), 'completos') 
    FAILED_FOLDER = os.path.join(os.getcwd(), 'falhas') 

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024 
    MAX_RETRIES = 3 
    FOLDER_MONITOR_INTERVAL_SECONDS = 60 

    # Feature Flags
    ENABLE_PDF_COMPRESSION = os.environ.get('ENABLE_PDF_COMPRESSION', 'True').lower() == 'false'
    ENABLE_OCR = os.environ.get('ENABLE_OCR', 'True').lower() == 'true'

    # External tool paths (adjust as needed for your environment)
    TESSERACT_CMD = os.environ.get('TESSERACT_CMD') or r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    POPPLER_PATH = os.environ.get('POPPLER_PATH') or r'C:\poppler\Library\bin'
    GHOSTSCRIPT_EXEC = os.environ.get('GHOSTSCRIPT_EXEC') or r'C:\Program Files\gs\gs10.05.1\bin\gswin64c.exe'
