from flask import Blueprint
from .handlers import GroupHandler

groups_bp = Blueprint('groups', __name__, url_prefix='/groups')
group_handler = GroupHandler()

groups_bp.route('/', methods=['GET'])(group_handler.list_groups)
groups_bp.route('/create', methods=['GET', 'POST'])(group_handler.create_group)
groups_bp.route('/<int:group_id>', methods=['GET', 'POST'])(group_handler.group_details)
groups_bp.route('/<int:group_id>/remove/<int:user_id>', methods=['POST'])(group_handler.remove_member)
groups_bp.route('/<int:group_id>/delete_file/<int:file_id>', methods=['POST'])(group_handler.delete_file)
