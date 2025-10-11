# routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from models import User, UserRole
from flask_login import login_user, logout_user, login_required, current_user
from .forms import LoginForm, RegistrationForm  # WICHTIG: Importiert die neuen Formulare

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        flash('Sie sind bereits angemeldet.', 'info')
        return redirect(url_for('jobs_bp.dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        # Die Validierung (z.B. ob User existiert) passiert jetzt im Formular
        new_user = User(username=form.username.data, role=UserRole.OPERATOR)
        new_user.set_password(form.password.data)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registrierung erfolgreich! Bitte melden Sie sich an.', 'success')
        return redirect(url_for('auth_bp.login'))
        
    # Übergebe das Form-Objekt an das Template
    return render_template('auth/register.html', form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('jobs_bp.dashboard'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        # Prüfe, ob User existiert und das Passwort korrekt ist
        if user and user.check_password(form.password.data):
            login_user(user, remember=True)
            flash(f'Erfolgreich angemeldet als {user.username}.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('jobs_bp.dashboard'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
            
    # Übergebe das Form-Objekt an das Template
    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sie wurden erfolgreich abgemeldet.', 'success')
    return redirect(url_for('auth_bp.login'))