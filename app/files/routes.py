from flask import Blueprint
from flask_login import login_required
from .handlers import FileHandler

# Cria o Blueprint de arquivos
files_bp = Blueprint('files', __name__)

# Instancia o manipulador de arquivos
file_handler = FileHandler()

# Define as rotas e as associa aos métodos do manipulador
# Aplica o decorador @login_required diretamente aqui
files_bp.route('/home')(login_required(file_handler.home))
files_bp.route('/upload', methods=['GET', 'POST'])(login_required(file_handler.upload_file))
files_bp.route('/data', methods=['GET', 'POST'])(login_required(file_handler.view_data))
files_bp.route('/download/<filename>')(login_required(file_handler.download_file))
files_bp.route('/delete/<int:file_id>', methods=['POST'])(login_required(file_handler.delete_file))