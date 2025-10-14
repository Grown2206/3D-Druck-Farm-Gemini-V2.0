import os
from flask import Flask, redirect, url_for
from flask_login import current_user, login_required
from dotenv import load_dotenv
from flask_migrate import Migrate
from sqlalchemy import inspect, text
import uuid
from flask_cors import CORS

from extensions import db, login_manager, socketio, csrf
from models import User, Job, PrinterStatus, JobStatus, UserRole, APIType, CameraSource, JobQuality, FilamentType, FilamentSpool, SystemSetting, Printer
import models
from scheduler import init_scheduler
from manage_db import export_data_command, import_data_command
from tests import test_suite_command
from routes import register_blueprints

def check_and_repair_database(app):
    """
    Überprüft die Datenbank auf häufige Inkonsistenzen nach Modelländerungen
    und führt bei Bedarf Reparaturen durch.
    """
    pass


def create_app():
    """Erstellt und konfiguriert die Flask-Anwendung."""
    
    load_dotenv()
    base_dir = os.path.abspath(os.path.dirname(__file__))

    app = Flask(__name__, instance_relative_config=True)
    CORS(app)
    
    # --- Konfiguration ---
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(app.instance_path, 'database.db')}",
        UPLOAD_FOLDER=os.path.join(base_dir, 'static', 'uploads'),
        PRINTER_IMAGES_FOLDER=os.path.join(base_dir, 'static', 'uploads', 'printer_images'),
        STL_FOLDER=os.path.join(base_dir, 'static', 'uploads', 'stl_files'),
        GCODE_FOLDER=os.path.join(base_dir, 'static', 'uploads', 'gcode'),
        SLICER_PROFILES_FOLDER=os.path.join(base_dir, 'slicer_profiles'),
        SNAPSHOT_FOLDER=os.path.join(base_dir, 'static', 'uploads', 'snapshots')
    )
    
    for folder in ['UPLOAD_FOLDER', 'PRINTER_IMAGES_FOLDER', 'STL_FOLDER', 'GCODE_FOLDER', 'SLICER_PROFILES_FOLDER', 'SNAPSHOT_FOLDER']:
        os.makedirs(app.config[folder], exist_ok=True)
        
    instance_path = app.instance_path
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)

    # --- Initialisierung der Extensions ---
    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth_bp.login'
    csrf.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")

    # --- Blueprints registrieren ---
    register_blueprints(app)

    # --- CLI-Befehle hinzufügen ---
    app.cli.add_command(export_data_command)
    app.cli.add_command(import_data_command)
    app.cli.add_command(test_suite_command)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_global_vars():
        """Stellt globale Variablen für alle Templates zur Verfügung."""
        if not current_user.is_authenticated:
            return {}
            
        low_stock_filaments = FilamentType.query.filter(
            FilamentType.reorder_level_g != None,
            FilamentType.reorder_level_g > 0
        ).all()
        
        triggered_alerts = [
            ftype for ftype in low_stock_filaments 
            if ftype and ftype.total_remaining_weight <= ftype.reorder_level_g
        ]
        
        return dict(
            models=models,
            PrinterStatus=PrinterStatus,
            JobStatus=JobStatus,
            UserRole=UserRole,
            APIType=APIType,
            CameraSource=CameraSource,
            JobQuality=JobQuality,
            Printer=Printer,
            current_user=current_user,
            low_stock_materials=triggered_alerts
        )
    
    @app.route('/')
    @login_required
    def index():
        return redirect(url_for('jobs_bp.dashboard'))

    with app.app_context():
        check_and_repair_database(app)
        
        if not os.path.exists(os.path.join(instance_path, "database.db")):
             db.create_all()
             if User.query.count() == 0:
                admin = User(username='admin', role=UserRole.ADMIN)
                admin.set_password('admin')
                db.session.add(admin)
                db.session.commit()
                print("--- Admin-Benutzer wurde mit Standard-Passwort 'admin' erstellt. ---")

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduler(app, socketio)
    
    return app

if __name__ == '__main__':
    app = create_app()
    socketio.run(app, debug=True, use_reloader=True, allow_unsafe_werkzeug=True)