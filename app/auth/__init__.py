from flask import Blueprint
from .handlers import AuthHandler

# Cria o Blueprint de autenticação
auth_bp = Blueprint('auth', __name__)

# Instancia o manipulador de autenticação
auth_handler = AuthHandler()

# Define as rotas e as associa aos métodos do manipulador
auth_bp.route('/login', methods=['GET', 'POST'])(auth_handler.login)
auth_bp.route('/logout', methods=['GET'])(auth_handler.logout)
auth_bp.route('/register', methods=['GET', 'POST'])(auth_handler.register)
auth_bp.route('/reset_password', methods=['GET', 'POST'], endpoint='forgot_password')(auth_handler.forgot_password)
auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'], endpoint='reset_password')(auth_handler.reset_password)