import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_key_that_should_be_changed'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///site.db'
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
