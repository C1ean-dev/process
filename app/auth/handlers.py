from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.models import User, db
from app.auth.forms import LoginForm, RegistrationForm
import logging
from datetime import datetime, timedelta

# Dicionário para armazenar tentativas de login falhas
# Idealmente, isso seria movido para um armazenamento mais persistente como Redis em produção
failed_login_tracker = {}

logger = logging.getLogger(__name__)

class AuthHandler:
    """
    Encapsula a lógica de manipulação de autenticação de usuário.
    """

    def login(self):
        if current_user.is_authenticated:
            return redirect(url_for('files.home'))

        form = LoginForm()
        if form.validate_on_submit():
            email = form.email.data
            
            if self._is_user_locked_out(email):
                remaining_time = self._get_remaining_lockout_time(email)
                flash(f'Too many failed login attempts. Please try again in {int(remaining_time.total_seconds())} seconds.', 'danger')
                logger.warning(f"Login attempt for '{email}' blocked due to lockout.")
                return render_template('login.html', title='Login', form=form)

            user = User.query.filter_by(email=email).first()

            if user and user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                self._clear_failed_attempts(email)
                logger.info(f"User '{user.username}' logged in.")
                next_page = request.args.get('next')
                return redirect(next_page or url_for('files.home'))
            else:
                self._record_failed_attempt(email)
                flash('Login Unsuccessful. Please check email and password', 'danger')
                
        return render_template('login.html', title='Login', form=form)

    def logout(self):
        logger.info(f"User '{current_user.username}' logged out.")
        logout_user()
        return redirect(url_for('auth.login'))

    def register(self):
        if not current_user.is_admin:
            flash('You do not have permission to register new users.', 'danger')
            return redirect(url_for('files.home'))

        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(
                username=form.username.data,
                email=form.email.data,
                is_admin=False
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            logger.info(f"New user '{form.username.data}' registered by admin '{current_user.username}'.")
            flash('Account created successfully!', 'success')
            return redirect(url_for('auth.login'))
            
        return render_template('register.html', title='Register', form=form)

    # Métodos auxiliares para controle de lockout
    def _is_user_locked_out(self, email):
        tracker = failed_login_tracker.get(email)
        if not tracker or tracker['attempts'] < 10:
            return False
        
        time_since_lockout = datetime.now() - tracker['lockout_time']
        if time_since_lockout < timedelta(minutes=1):
            return True
        else:
            # Lockout expirou
            self._clear_failed_attempts(email)
            return False

    def _get_remaining_lockout_time(self, email):
        tracker = failed_login_tracker.get(email, {})
        lockout_time = tracker.get('lockout_time')
        if not lockout_time:
            return timedelta(0)
            
        time_since_lockout = datetime.now() - lockout_time
        remaining_time = timedelta(minutes=1) - time_since_lockout
        return remaining_time if remaining_time.total_seconds() > 0 else timedelta(0)

    def _record_failed_attempt(self, email):
        if email not in failed_login_tracker:
            failed_login_tracker[email] = {'attempts': 0, 'lockout_time': None}
        
        failed_login_tracker[email]['attempts'] += 1
        logger.warning(f"Failed login attempt for '{email}'. Attempts: {failed_login_tracker[email]['attempts']}")

        if failed_login_tracker[email]['attempts'] >= 10:
            failed_login_tracker[email]['lockout_time'] = datetime.now()
            flash('Too many failed login attempts. You are temporarily locked out for 1 minute.', 'danger')
            logger.warning(f"User '{email}' locked out due to too many failed attempts.")

    def _clear_failed_attempts(self, email):
        if email in failed_login_tracker:
            del failed_login_tracker[email]
