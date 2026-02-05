from flask import render_template, redirect, url_for, flash, abort
from app.models import db, User
from app.auth.forms import RegistrationForm
import logging

logger = logging.getLogger(__name__)

class SetupHandler:
    """
    Encapsula a lógica para a configuração inicial do administrador.
    """

    def setup_admin(self):
        # Se um administrador já existe, a rota não deve mais estar acessível.
        if User.query.filter_by(is_admin=True).first():
            logger.warning("Attempt to access setup_admin when admin already exists.")
            abort(404)

        form = RegistrationForm()
        if form.validate_on_submit():
            try:
                admin_user = User(
                    username=form.username.data,
                    email=form.email.data,
                    is_admin=True
                )
                admin_user.set_password(form.password.data)
                db.session.add(admin_user)
                db.session.commit()
                
                logger.info(f"Admin user '{form.username.data}' created successfully.")
                flash('Admin account created successfully! Please log in.', 'success')
                return redirect(url_for('auth.login'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error creating admin user: {e}", exc_info=True)
                flash('An error occurred while creating the admin account. Please try again.', 'danger')

        return render_template('setup_admin.html', title='Setup Admin Account', form=form)
