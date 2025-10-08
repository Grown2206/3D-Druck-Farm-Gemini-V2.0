from flask import Blueprint, render_template, request, redirect, url_for, flash
# KORREKTUR: Importiert die zentrale DB-Instanz
from extensions import db
from models import User, UserRole
from flask_login import login_user, logout_user, login_required, current_user

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        flash('Sie sind bereits angemeldet.', 'info')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
             flash('Benutzername und Passwort sind erforderlich.', 'danger')
             return render_template('auth/register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Benutzername existiert bereits.', 'warning')
            return render_template('auth/register.html')
            
        # WIEDERHERGESTELLT: Jeder neue Benutzer ist ein Operator. Nur der initiale Admin wird in app.py erstellt.
        new_user = User(username=username, role=UserRole.OPERATOR)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registrierung erfolgreich! Bitte melden Sie sich an.', 'success')
        return redirect(url_for('auth_bp.login'))
        
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash('Sie sind bereits angemeldet.', 'info')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Erfolgreich angemeldet als {user.username}.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sie wurden abgemeldet.', 'info')
    return redirect(url_for('auth_bp.login'))

