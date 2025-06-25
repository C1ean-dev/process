import os
import uuid
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory
from flask_login import login_required, current_user
from app.files.forms import FileUploadForm, SearchForm
from app.models import db, File
from werkzeug.utils import secure_filename
from sqlalchemy import or_

logger = logging.getLogger(__name__)

files_bp = Blueprint('files', __name__)

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
        uploaded_files = request.files.getlist('file')
        
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
    query = request.args.get('query', '')
    filter_field = request.args.get('filter', 'nome')

    if search_form.validate_on_submit():
        query = search_form.query.data
        filter_field = search_form.filter.data
        return redirect(url_for('files.view_data', query=query, filter=filter_field))

    files_query = File.query.filter(File.status.in_(['completed', 'failed'])).order_by(File.upload_date.desc())

    if query:
        search_pattern = f"%{query}%"
        if filter_field == 'equipamentos':
            files_query = files_query.filter(File.equipamentos.ilike(search_pattern))
        elif filter_field == 'imei_numbers':
            files_query = files_query.filter(File.imei_numbers.ilike(search_pattern))
        elif filter_field == 'patrimonio_numbers':
            files_query = files_query.filter(File.patrimonio_numbers.ilike(search_pattern))
        elif filter_field == 'processed_data':
            files_query = files_query.filter(File.processed_data.ilike(search_pattern))
        elif filter_field == 'matricula':
            files_query = files_query.filter(File.matricula.ilike(search_pattern))
        elif filter_field == 'funcao':
            files_query = files_query.filter(File.funcao.ilike(search_pattern))
        elif filter_field == 'empregador':
            files_query = files_query.filter(File.empregador.ilike(search_pattern))
        elif filter_field == 'rg':
            files_query = files_query.filter(File.rg.ilike(search_pattern))
        elif filter_field == 'cpf':
            files_query = files_query.filter(File.cpf.ilike(search_pattern))
        else:
            files_query = files_query.filter(File.nome.ilike(search_pattern))
        
        flash(f"Showing results for '{query}' in '{filter_field}'", 'info')
    else:
        # If no query, filter out results where the selected field is not null or empty
        if filter_field == 'equipamentos':
            files_query = files_query.filter(File.equipamentos != None, File.equipamentos != '', File.equipamentos != '[]')
        elif filter_field == 'imei_numbers':
            files_query = files_query.filter(File.imei_numbers != None, File.imei_numbers != '', File.imei_numbers != '[]')
        elif filter_field == 'patrimonio_numbers':
            files_query = files_query.filter(File.patrimonio_numbers != None, File.patrimonio_numbers != '', File.patrimonio_numbers != '[]')
        elif filter_field == 'processed_data':
            files_query = files_query.filter(File.processed_data != None, File.processed_data != '')
        elif filter_field == 'matricula':
            files_query = files_query.filter(File.matricula != None, File.matricula != '', File.matricula != 'N/A')
        elif filter_field == 'funcao':
            files_query = files_query.filter(File.funcao != None, File.funcao != '')
        elif filter_field == 'empregador':
            files_query = files_query.filter(File.empregador != None, File.empregador != '')
        elif filter_field == 'rg':
            files_query = files_query.filter(File.rg != None, File.rg != '')
        elif filter_field == 'cpf':
            files_query = files_query.filter(File.cpf != None, File.cpf != '')
        else: # Default to 'nome'
            files_query = files_query.filter(File.nome != None, File.nome != '', File.nome != 'N/A')

    files = files_query.all()
    return render_template('data.html', title='View Data', files=files, search_form=search_form, current_query=query, current_filter=filter_field)

import boto3
from botocore.exceptions import ClientError

@files_bp.route('/download/<filename>')
@login_required
def download_file(filename):
    file_record = File.query.filter_by(filename=filename).first()
    if not file_record:
        flash('File not found.', 'danger')
        return redirect(url_for('files.view_data'))
    
    if file_record.user_id != current_user.id and not current_user.is_admin:
        flash('You are not authorized to download this file.', 'danger')
        return redirect(url_for('files.view_data'))

    if file_record.status == 'completed':
        s3_client = boto3.client(
            service_name='s3',
            endpoint_url=current_app.config['CLOUDFLARE_R2_ENDPOINT_URL'],
            aws_access_key_id=current_app.config['CLOUDFLARE_R2_ACCESS_KEY_ID'],
            aws_secret_access_key=current_app.config['CLOUDFLARE_R2_SECRET_ACCESS_KEY'],
            region_name='auto'
        )
        bucket_name = current_app.config['CLOUDFLARE_R2_BUCKET_NAME']
        object_name = file_record.filename

        try:
            object_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_name},
                ExpiresIn=60
            )
            logger.info(f"Generated presigned URL for download: {object_url}")
            return redirect(object_url)
        except ClientError as e:
            flash(f"Error generating presigned URL: {e}", 'danger')
            logger.error(f"Error generating presigned URL: {e}", exc_info=True)
            return redirect(url_for('files.view_data'))
    else:
        flash('File is not yet completed.', 'danger')
        return redirect(url_for('files.view_data'))

# Removed worker_status route as it will be in app/workers/routes.py
