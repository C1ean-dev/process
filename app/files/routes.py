import os
import uuid
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory # Import send_from_directory
from flask_login import login_required, current_user
from app.files.forms import FileUploadForm, SearchForm # Import forms from new path
from app.models import db, File
from werkzeug.utils import secure_filename
from sqlalchemy import or_ # Import or_ for OR conditions in queries

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__) # Renamed blueprint to 'files'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@files_bp.route('/home')
@login_required
def home():
    return render_template('home.html', title='Home')

@files_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    form = FileUploadForm()
    if request.method == 'POST':
        uploaded_files = request.files.getlist('file') # Get all files from the 'file' input
        
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            flash('No selected file(s)', 'danger')
            return redirect(request.url)

        successful_uploads = 0
        for file in uploaded_files:
            if file and allowed_file(file.filename):
                original_filename = secure_filename(file.filename)
                unique_filename = str(uuid.uuid4()) + os.path.splitext(original_filename)[1]
                
                file_path_in_uploads = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path_in_uploads)

                # Move file from UPLOAD_FOLDER to PENDING_FOLDER immediately after upload
                file_path_in_pending = os.path.join(current_app.config['PENDING_FOLDER'], unique_filename)
                try:
                    os.rename(file_path_in_uploads, file_path_in_pending)
                    logger.info(f"File '{original_filename}' moved from UPLOAD_FOLDER to PENDING_FOLDER.")
                except Exception as e:
                    flash(f"Error moving file {original_filename} to pending folder: {e}. Please try again.", 'danger')
                    logger.error(f"Error moving file {original_filename} from {file_path_in_uploads} to {file_path_in_pending}: {e}")
                    # Attempt to clean up the file from UPLOAD_FOLDER if the move failed
                    if os.path.exists(file_path_in_uploads):
                        try:
                            os.remove(file_path_in_uploads)
                            logger.info(f"Cleaned up '{original_filename}' from UPLOAD_FOLDER after failed move.")
                        except Exception as cleanup_e:
                            logger.error(f"Error cleaning up file {original_filename} from UPLOAD_FOLDER: {cleanup_e}")
                    continue # Skip to next file if move fails

                new_file = File(
                    filename=unique_filename,
                    original_filename=original_filename,
                    filepath=file_path_in_pending, # Filepath now points to PENDING_FOLDER
                    user_id=current_user.id,
                    status='pending'
                )
                db.session.add(new_file)
                db.session.commit()

                task_queue = current_app.config['TASK_QUEUE']
                # Pass the initial retry count (0) and the filepath in PENDING_FOLDER
                task_queue.put((new_file.id, new_file.filepath, new_file.retries))
                successful_uploads += 1
                logger.info(f"File '{original_filename}' uploaded by '{current_user.username}' and added to processing queue (in PENDING_FOLDER).")
            else:
                flash(f'Skipped invalid file: {file.filename}. Allowed types are: png, jpg, jpeg, gif, pdf', 'warning')
        
        if successful_uploads > 0:
            flash(f'{successful_uploads} file(s) uploaded successfully and added to processing queue!', 'success')
        else:
            flash('No files were uploaded successfully.', 'danger')
            
        return redirect(url_for('files.upload_file'))
    return render_template('upload.html', title='Upload File', form=form)

@files_bp.route('/data', methods=['GET', 'POST'])
@login_required
def view_data():
    search_form = SearchForm()
    query = request.args.get('query', '') # Get query from URL parameter for GET requests
    
    if search_form.validate_on_submit():
        query = search_form.query.data
        # Redirect to GET request with query parameter to make URL shareable
        return redirect(url_for('files.view_data', query=query)) # Updated url_for

    # Filter by 'completed' status by default
    files_query = File.query.filter_by(status='completed').order_by(File.upload_date.desc())

    if query:
        search_pattern = f"%{query}%"
        files_query = files_query.filter(
            File.processed_data.ilike(search_pattern)
        )
        flash(f"Showing results for '{query}' in processed data", 'info')
    
    files = files_query.all()
    return render_template('data.html', title='View Data', files=files, search_form=search_form, current_query=query)

@files_bp.route('/download/<filename>')
@login_required
def download_file(filename):
    # Ensure the file is in the COMPLETED_FOLDER and belongs to the current user (or is admin)
    file_record = File.query.filter_by(filename=filename).first()
    if not file_record:
        flash('File not found.', 'danger')
        return redirect(url_for('files.view_data'))
    
    # Basic authorization: only owner or admin can download
    if file_record.user_id != current_user.id and not current_user.is_admin:
        flash('You are not authorized to download this file.', 'danger')
        return redirect(url_for('files.view_data'))

    # Check if the file is actually in the completed folder
    if file_record.status == 'completed' and os.path.exists(file_record.filepath):
        # Ensure the filepath is within the COMPLETED_FOLDER for security
        if os.path.dirname(file_record.filepath) == current_app.config['COMPLETED_FOLDER']:
            return send_from_directory(current_app.config['COMPLETED_FOLDER'], filename, as_attachment=True)
        else:
            flash('File is not in the completed folder or path is incorrect.', 'danger')
            logger.error(f"Attempt to download file {filename} with incorrect path: {file_record.filepath}")
            return redirect(url_for('files.view_data'))
    else:
        flash('File is not yet completed or does not exist.', 'danger')
        return redirect(url_for('files.view_data'))

# Removed worker_status route as it will be in app/workers/routes.py
