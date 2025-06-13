from flask import Blueprint, render_template, redirect, url_for, flash
from app.models import db, User
from app.auth.forms import RegistrationForm # Import form from new path
import logging

logger = logging.getLogger(__name__)

setup_bp = Blueprint('setup', __name__)

@setup_bp.route('/setup', methods=['GET', 'POST'])
def setup_admin():
    # Check if an admin already exists. If so, redirect to login.
    if User.query.filter_by(is_admin=True).first():
        flash('Admin user already exists. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data

        # Create the first admin user
        admin_user = User(username=username, email=email, is_admin=True)
        admin_user.set_password(password)
        db.session.add(admin_user)
        db.session.commit()
        logger.info(f"Admin user '{username}' created successfully.")
        flash('Admin account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('setup_admin.html', title='Setup Admin Account', form=form)
