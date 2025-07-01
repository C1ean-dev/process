import os
import uuid
import logging
import boto3
from botocore.exceptions import ClientError
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from app.models import db, File
from .forms import FileUploadForm, SearchForm

logger = logging.getLogger(__name__)

class FileHandler:
    """
    Encapsula a lógica de manipulação de arquivos (upload, visualização, etc.).
    """

    def _allowed_file(self, filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

    def home(self):
        return render_template('home.html', title='Home')

    def upload_file(self):
        form = FileUploadForm()
        if request.method == 'POST':
            uploaded_files = request.files.getlist('file')
            
            if not uploaded_files or all(f.filename == '' for f in uploaded_files):
                flash('No selected file(s)', 'danger')
                return redirect(request.url)

            successful_uploads = self._process_uploaded_files(uploaded_files)
            
            if successful_uploads > 0:
                flash(f'{successful_uploads} file(s) uploaded successfully and added to processing queue!', 'success')
            else:
                flash('No files were uploaded successfully.', 'danger')
                
            return redirect(url_for('files.upload_file'))
            
        return render_template('upload.html', title='Upload File', form=form)

    def _process_uploaded_files(self, files):
        successful_uploads = 0
        for file in files:
            if file and self._allowed_file(file.filename):
                original_filename = secure_filename(file.filename)
                unique_filename = str(uuid.uuid4()) + os.path.splitext(original_filename)[1]
                file_path_in_uploads = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                
                file.save(file_path_in_uploads)

                new_file = File(
                    filename=unique_filename,
                    original_filename=original_filename,
                    filepath=file_path_in_uploads,
                    user_id=current_user.id,
                    status='pending'
                )
                db.session.add(new_file)
                db.session.commit()

                task_queue = current_app.config['TASK_QUEUE']
                task_queue.put((new_file.id, new_file.filepath, new_file.retries))
                successful_uploads += 1
                logger.info(f"File '{original_filename}' uploaded by '{current_user.username}' and added to queue.")

                # O arquivo local é removido na task do worker após o upload para o R2
            else:
                flash(f'Skipped invalid file: {file.filename}. Allowed types are: png, jpg, jpeg, gif, pdf', 'warning')
        return successful_uploads

    def view_data(self):
        search_form = SearchForm()
        query = request.args.get('query', '')
        filter_field = request.args.get('filter', 'nome')

        if search_form.validate_on_submit():
            query = search_form.query.data
            filter_field = search_form.filter.data
            return redirect(url_for('files.view_data', query=query, filter=filter_field))

        files_query = self._build_data_query(query, filter_field)
        files = files_query.all()
        
        if query:
            flash(f"Showing results for '{query}' in '{filter_field}'", 'info')

        return render_template('data.html', title='View Data', files=files, search_form=search_form, current_query=query, current_filter=filter_field)

    def _build_data_query(self, query, filter_field):
        files_query = File.query.filter(File.status.in_(['completed', 'failed'])).order_by(File.upload_date.desc())
        
        if not query:
            return files_query

        search_pattern = f"%{query}%"
        filter_map = {
            'equipamentos': File.equipamentos,
            'imei_numbers': File.imei_numbers,
            'patrimonio_numbers': File.patrimonio_numbers,
            'processed_data': File.processed_data,
            'matricula': File.matricula,
            'funcao': File.funcao,
            'empregador': File.empregador,
            'rg': File.rg,
            'cpf': File.cpf,
            'nome': File.nome
        }

        column_to_filter = filter_map.get(filter_field, File.nome)
        return files_query.filter(column_to_filter.ilike(search_pattern))

    def download_file(self, filename):
        file_record = File.query.filter_by(filename=filename).first()
        if not file_record:
            flash('File not found.', 'danger')
            return redirect(url_for('files.view_data'))
        
        if file_record.user_id != current_user.id and not current_user.is_admin:
            flash('You are not authorized to download this file.', 'danger')
            return redirect(url_for('files.view_data'))

        if file_record.status != 'completed':
            flash('File is not yet completed and cannot be downloaded.', 'warning')
            return redirect(url_for('files.view_data'))

        try:
            s3_client = self._get_r2_client()
            bucket_name = current_app.config['CLOUDFLARE_R2_BUCKET_NAME']
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_record.filename},
                ExpiresIn=60  # URL válida por 60 segundos
            )
            logger.info(f"Generated presigned URL for download: {presigned_url}")
            return redirect(presigned_url)
        except ClientError as e:
            flash(f"Error generating download link: {e}", 'danger')
            logger.error(f"Error generating presigned URL: {e}", exc_info=True)
            return redirect(url_for('files.view_data'))

    def _get_r2_client(self):
        return boto3.client(
            service_name='s3',
            endpoint_url=current_app.config['CLOUDFLARE_R2_ENDPOINT_URL'],
            aws_access_key_id=current_app.config['CLOUDFLARE_R2_ACCESS_KEY_ID'],
            aws_secret_access_key=current_app.config['CLOUDFLARE_R2_SECRET_ACCESS_KEY'],
            region_name='auto'
        )