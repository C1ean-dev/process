from flask import Blueprint
from flask_login import login_required
from .handlers import EditorHandler

# Cria o Blueprint do editor
editor_bp = Blueprint('editor', __name__)

# Instancia o manipulador do editor
editor_handler = EditorHandler()

# Define as rotas
editor_bp.route('/termos')(login_required(editor_handler.list_termos))
editor_bp.route('/termos/edit/<filename>')(login_required(editor_handler.edit_termo))
editor_bp.route('/termos/save', methods=['POST'])(login_required(editor_handler.save_termo))
