from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from flask_mail import Message
from app.models import User, db, record_metric
from app.auth.forms import LoginForm, RegistrationForm, RequestResetForm, ResetPasswordForm, MagicLinkForm, CompleteRegistrationForm
import logging
from datetime import datetime, timedelta, timezone
from itsdangerous import URLSafeTimedSerializer as Serializer
from werkzeug.security import generate_password_hash

# Dicionário para armazenar tentativas de login falhas
# Idealmente, isso seria movido para um armazenamento mais persistente como Redis em produção
failed_login_tracker = {}
# Tracker para rate limit de reset de senha
reset_request_tracker = {}

logger = logging.getLogger(__name__)

DUMMY_HASH = generate_password_hash("dummy_password")

class AuthHandler:
    """
    Encapsula a lógica de manipulação de autenticação de usuário.
    """

    def _send_email(self, subject, recipients, html_body):
        from app import mail
        msg = Message(subject, recipients=recipients)
        msg.html = html_body
        try:
            mail.send(msg)
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def request_magic_link(self):
        if current_user.is_authenticated:
            return redirect(url_for('files.home'))
        form = MagicLinkForm()
        if form.validate_on_submit():
            email = form.email.data
            s = Serializer(current_app.config['SECRET_KEY'])
            token = s.dumps({'email': email})
            magic_link = url_for('auth.complete_registration', token=token, _external=True)
            
            # Enviar e-mail real
            subject = "Register your account - File Processor"
            html_body = render_template('auth/email_magic_link.html', magic_link=magic_link)
            
            if self._send_email(subject, [email], html_body):
                flash('A magic link has been sent to your email. Check your inbox.', 'info')
                logger.info(f"Magic link sent to {email}")
            else:
                flash('Failed to send magic link. Please try again later or contact support.', 'danger')
                logger.error(f"Failed to send magic link to {email}")

            return redirect(url_for('auth.login'))
        return render_template('auth/request_magic_link.html', title='Register', form=form)

    def complete_registration(self, token):
        if current_user.is_authenticated:
            return redirect(url_for('files.home'))
        
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            # Token válido por 1 hora para registro
            email = s.loads(token, max_age=3600)['email']
        except:
            flash('The magic link is invalid or has expired.', 'warning')
            return redirect(url_for('auth.request_magic_link'))
            
        # Verifica se o usuário já existe (caso tenha clicado duas vezes no link)
        if User.query.filter_by(email=email).first():
            flash('This email is already registered. Please log in.', 'info')
            return redirect(url_for('auth.login'))

        form = CompleteRegistrationForm()
        if form.validate_on_submit():
            user = User(
                username=form.username.data,
                email=email,
                is_admin=False
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            logger.info(f"User '{form.username.data}' registered via magic link ({email}).")
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
            
        return render_template('auth/complete_registration.html', title='Complete Registration', form=form, email=email)

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

            # Timing attack mitigation: always check a hash
            if user:
                password_correct = user.check_password(form.password.data)
            else:
                from werkzeug.security import check_password_hash
                check_password_hash(DUMMY_HASH, form.password.data)
                password_correct = False

            if password_correct:
                login_user(user, remember=form.remember.data)
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                record_metric('user_login', 1, {'user_id': user.id, 'username': user.username})
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

    def forgot_password(self):
        if current_user.is_authenticated:
            return redirect(url_for('files.home'))
        
        # IP-based Rate Limit for password reset (5 per minute)
        ip = request.remote_addr
        now = datetime.now()
        if ip not in reset_request_tracker:
            reset_request_tracker[ip] = []
        
        # Clean old attempts
        reset_request_tracker[ip] = [t for t in reset_request_tracker[ip] if now - t < timedelta(minutes=1)]
        
        if len(reset_request_tracker[ip]) >= 5:
            flash('Too many password reset requests. Please wait a minute.', 'danger')
            logger.warning(f"Rate limit hit for password reset from IP: {ip}")
            return render_template('forgot_password.html', title='Reset Password', form=RequestResetForm())

        form = RequestResetForm()
        if form.validate_on_submit():
            reset_request_tracker[ip].append(now)
            user = User.query.filter_by(email=form.email.data).first()
            token = user.get_reset_token()
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Enviar e-mail real
            subject = "Password Reset Request - File Processor"
            html_body = render_template('auth/email_reset_password.html', reset_url=reset_url)
            
            if self._send_email(subject, [user.email], html_body):
                flash('An email has been sent with instructions to reset your password.', 'info')
                logger.info(f"Password reset link sent to {user.email}")
            else:
                flash('Failed to send password reset email. Please try again later.', 'danger')
                logger.error(f"Failed to send reset link to {user.email}")
                
            return redirect(url_for('auth.login'))
        return render_template('forgot_password.html', title='Reset Password', form=form)

    def reset_password(self, token):
        if current_user.is_authenticated:
            return redirect(url_for('files.home'))
        user = User.verify_reset_token(token)
        if user is None:
            flash('That is an invalid or expired token', 'warning')
            return redirect(url_for('auth.forgot_password'))
        form = ResetPasswordForm()
        if form.validate_on_submit():
            user.set_password(form.password.data)
            db.session.commit()
            flash('Your password has been updated! You are now able to log in', 'success')
            return redirect(url_for('auth.login'))
        return render_template('reset_password.html', title='Reset Password', form=form)

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
