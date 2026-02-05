from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import File

workers_bp = Blueprint('workers', __name__, url_prefix='/workers')

@workers_bp.route('/status')
@login_required
def worker_status():
    user_query = File.query.filter_by(user_id=current_user.id)
    
    pending_count = user_query.filter_by(status='pending').count()
    processing_count = user_query.filter_by(status='processing').count()
    completed_count = user_query.filter_by(status='completed').count()
    failed_count = user_query.filter_by(status='failed').count()

    return render_template('worker_status.html', title='Worker Status',
                           pending_count=pending_count,
                           processing_count=processing_count,
                           completed_count=completed_count,
                           failed_count=failed_count)

