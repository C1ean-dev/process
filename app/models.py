from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin # Import UserMixin
import json

db = SQLAlchemy()

def record_metric(name, value, tags=None):
    """Record a metric in the database."""
    tags_json = json.dumps(tags) if tags else None
    metric = Metric(name=name, value=value, tags=tags_json)
    db.session.add(metric)
    db.session.commit()

class User(db.Model, UserMixin): # Inherit UserMixin
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    registration_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    modified_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    # Required by Flask-Login
    @property
    def is_active(self):
        return True # All users are active

    @property
    def is_authenticated(self):
        return True # User is authenticated if logged in

    @property
    def is_anonymous(self):
        return False # User is not anonymous if logged in

    def get_id(self):
        return str(self.id) # Return user ID as string

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    filepath = db.Column(db.String(512), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending') # pending, processing, completed, failed
    checksum = db.Column(db.String(256), nullable=True) # Add checksum column
    retries = db.Column(db.Integer, default=0) # New column for retry count
    processed_data = db.Column(db.Text) # Store OCR or other processed data (raw text)
    nome = db.Column(db.String(255), nullable=True)
    matricula = db.Column(db.String(255), nullable=True)
    funcao = db.Column(db.String(255), nullable=True)
    empregador = db.Column(db.String(255), nullable=True)
    rg = db.Column(db.String(255), nullable=True)
    cpf = db.Column(db.String(255), nullable=True)
    equipamentos = db.Column(db.Text, nullable=True) # Store as JSON string
    data_documento = db.Column(db.String(50), nullable=True) # Store date as string
    imei_numbers = db.Column(db.Text, nullable=True) # New column to store list of IMEI numbers as JSON string
    patrimonio_numbers = db.Column(db.Text, nullable=True) # New column to store list of Patrimonio numbers as JSON string

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('files', lazy=True))

    def __repr__(self):
        return f'<File {self.filename}>'

class Metric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    name = db.Column(db.String(255), nullable=False)
    value = db.Column(db.Float, nullable=False)
    tags = db.Column(db.Text, nullable=True)  # JSON string for additional metadata

    def __repr__(self):
        return f'<Metric {self.name} at {self.timestamp}>'
