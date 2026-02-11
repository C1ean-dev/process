from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user, login_required
from app.models import db, Group, User, File
from .forms import GroupForm, AddMemberForm
import logging
import os
import boto3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class GroupHandler:
    @login_required
    def list_groups(self):
        # Groups the user created or is a member of
        user_groups = current_user.groups.all()
        created_groups = Group.query.filter_by(creator_id=current_user.id).all()
        
        # Merge and remove duplicates
        all_groups = list(set(user_groups + created_groups))
        
        return render_template('groups/list.html', title='My Groups', groups=all_groups)

    @login_required
    def create_group(self):
        form = GroupForm()
        if form.validate_on_submit():
            group = Group(
                name=form.name.data,
                description=form.description.data,
                creator_id=current_user.id
            )
            # Creator is automatically a member
            group.members.append(current_user)
            db.session.add(group)
            db.session.commit()
            flash(f'Group "{group.name}" created successfully!', 'success')
            return redirect(url_for('groups.list_groups'))
        return render_template('groups/create.html', title='Create Group', form=form)

    @login_required
    def group_details(self, group_id):
        group = Group.query.get_or_404(group_id)
        
        # Security check: User must be a member
        if current_user not in group.members and not current_user.is_admin:
            flash('You do not have permission to view this group.', 'danger')
            return redirect(url_for('groups.list_groups'))
            
        add_form = AddMemberForm()
        if add_form.validate_on_submit():
            user_to_add = User.query.filter_by(email=add_form.email.data).first()
            if user_to_add in group.members:
                flash('User is already a member of this group.', 'info')
            else:
                group.members.append(user_to_add)
                db.session.commit()
                flash(f'User {user_to_add.username} added to group.', 'success')
            return redirect(url_for('groups.group_details', group_id=group.id))
            
        # Group files: 
        # Creators see everything (including soft-deleted)
        # Others see only non-deleted
        if group.creator_id == current_user.id or current_user.is_admin:
            files = File.query.filter_by(group_id=group.id).all()
        else:
            files = File.query.filter_by(group_id=group.id, is_deleted=False).all()
            
        return render_template('groups/details.html', title=group.name, group=group, form=add_form, files=files)

    @login_required
    def remove_member(self, group_id, user_id):
        group = Group.query.get_or_404(group_id)
        
        # Only creator can remove members
        if group.creator_id != current_user.id and not current_user.is_admin:
            flash('Only the group creator can remove members.', 'danger')
            return redirect(url_for('groups.group_details', group_id=group.id))
            
        user_to_remove = User.query.get_or_404(user_id)
        if user_to_remove == group.creator:
            flash('The creator cannot be removed from the group.', 'danger')
        elif user_to_remove in group.members:
            group.members.remove(user_to_remove)
            db.session.commit()
            flash(f'User {user_to_remove.username} removed from group.', 'success')
        
        return redirect(url_for('groups.group_details', group_id=group.id))

    @login_required
    def delete_file(self, group_id, file_id):
        group = Group.query.get_or_404(group_id)
        file_to_delete = File.query.get_or_404(file_id)

        # Security check: User must be group creator or file owner or admin
        if group.creator_id != current_user.id and file_to_delete.user_id != current_user.id and not current_user.is_admin:
            flash('You do not have permission to delete this file.', 'danger')
            return redirect(url_for('groups.group_details', group_id=group.id))

        if file_to_delete.group_id != group.id:
            flash('File does not belong to this group.', 'danger')
            return redirect(url_for('groups.group_details', group_id=group.id))

        try:
            # If user is NOT the group creator/admin, perform a SOFT delete
            if group.creator_id != current_user.id and not current_user.is_admin:
                file_to_delete.is_deleted = True
                file_to_delete.deleted_at = datetime.now(timezone.utc)
                db.session.commit()
                flash(f'File "{file_to_delete.original_filename}" marked as deleted. Only the group owner can restore or permanently delete it.', 'info')
                return redirect(url_for('groups.group_details', group_id=group.id))

            # If user IS the creator/admin, perform a PERMANENT delete
            # Delete from R2 if applicable
            if current_app.config['R2_FEATURE_FLAG'] == 'True' and file_to_delete.status == 'completed':
                try:
                    s3_client = boto3.client(
                        service_name='s3',
                        endpoint_url=current_app.config['CLOUDFLARE_R2_ENDPOINT_URL'],
                        aws_access_key_id=current_app.config['CLOUDFLARE_R2_ACCESS_KEY_ID'],
                        aws_secret_access_key=current_app.config['CLOUDFLARE_R2_SECRET_ACCESS_KEY'],
                        region_name='auto'
                    )
                    s3_client.delete_object(Bucket=current_app.config['CLOUDFLARE_R2_BUCKET_NAME'], Key=file_to_delete.filename)
                    logger.info(f"Deleted file {file_to_delete.filename} from R2.")
                except Exception as e:
                    logger.error(f"Failed to delete file from R2: {e}")

            # Delete local file if it exists
            if os.path.exists(file_to_delete.filepath):
                os.remove(file_to_delete.filepath)
                logger.info(f"Deleted local file {file_to_delete.filepath}")

            db.session.delete(file_to_delete)
            db.session.commit()
            flash(f'File "{file_to_delete.original_filename}" permanently deleted.', 'success')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting file {file_id}: {e}", exc_info=True)
            flash('An error occurred while deleting the file.', 'danger')

        return redirect(url_for('groups.group_details', group_id=group.id))

    @login_required
    def restore_file(self, group_id, file_id):
        group = Group.query.get_or_404(group_id)
        file_to_restore = File.query.get_or_404(file_id)

        # Only group creator or admin can restore
        if group.creator_id != current_user.id and not current_user.is_admin:
            flash('Only the group owner can restore files.', 'danger')
            return redirect(url_for('groups.group_details', group_id=group.id))

        if file_to_restore.group_id != group.id:
            flash('File does not belong to this group.', 'danger')
            return redirect(url_for('groups.group_details', group_id=group.id))

        file_to_restore.is_deleted = False
        file_to_restore.deleted_at = None
        db.session.commit()
        flash(f'File "{file_to_restore.original_filename}" has been restored.', 'success')
        return redirect(url_for('groups.group_details', group_id=group.id))
