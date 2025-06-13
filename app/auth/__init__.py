from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.auth.forms import LoginForm, RegistrationForm # Import forms from new path
from app.models import db
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('files.home')) # Redirect to home if already logged in

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            logger.info(f"User '{user.username}' logged in.")
            return redirect(next_page or url_for('files.home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logger.info(f"User '{current_user.username}' logged out.")
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    # Only admin can register new users
    if not current_user.is_admin:
        flash('You do not have permission to register new users.', 'danger')
        return redirect(url_for('files.home')) # Redirect to files.home

    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data

        user = User(username=username, email=email, is_admin=False) # New users are not admins by default
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        logger.info(f"New user '{username}' registered by admin '{current_user.username}'.")
        flash('Account created successfully!', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', title='Register', form=form)
