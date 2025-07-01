from flask import Blueprint
from .handlers import SetupHandler

# Cria o Blueprint de configuração
setup_bp = Blueprint('setup', __name__)

# Instancia o manipulador de configuração
setup_handler = SetupHandler()

# Define a rota e a associa ao método do manipulador
setup_bp.route('/setup', methods=['GET', 'POST'])(setup_handler.setup_admin)