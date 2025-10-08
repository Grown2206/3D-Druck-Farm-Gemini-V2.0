# /routes/slicer_profiles.py
import os
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from extensions import db
from models import SlicerProfile, Printer, FilamentType
from flask_login import login_required
from .forms import update_model_from_form
from sqlalchemy import distinct

slicer_profiles_bp = Blueprint('slicer_profiles_bp', __name__)

def allowed_profile_file(filename):
    """Überprüft, ob die hochgeladene Datei eine .ini-Datei ist."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'ini'}

def save_profile_file(file):
    """Speichert die hochgeladene Profildatei und gibt den einzigartigen Dateinamen zurück."""
    filename = secure_filename(file.filename)
    unique_filename = f"{secrets.token_hex(8)}_{filename}"
    file_path = os.path.join(current_app.config['SLICER_PROFILES_FOLDER'], unique_filename)
    file.save(file_path)
    return unique_filename

def delete_profile_file(filename):
    """Löscht eine alte Profildatei."""
    if filename:
        try:
            os.remove(os.path.join(current_app.config['SLICER_PROFILES_FOLDER'], filename))
        except OSError:
            pass

@slicer_profiles_bp.route('/')
@login_required
def list_profiles():
    profiles = SlicerProfile.query.order_by(SlicerProfile.name).all()
    printers = Printer.query.order_by(Printer.name).all()
    filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    
    return render_template('slicer/profiles.html', 
                           profiles=profiles, 
                           printers=printers,
                           filament_types=filament_types,
                           form_title="Neues Slicer-Profil erstellen", 
                           profile_to_edit=None)

@slicer_profiles_bp.route('/add', methods=['POST'])
@login_required
def add_profile():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Ein Profilname ist erforderlich.', 'danger')
        return redirect(url_for('slicer_profiles_bp.list_profiles'))

    try:
        new_profile = SlicerProfile(name=name)
        
        if 'profile_file' in request.files:
            file = request.files['profile_file']
            if file and file.filename != '' and allowed_profile_file(file.filename):
                unique_filename = save_profile_file(file)
                new_profile.filename = unique_filename
            elif file.filename != '':
                flash('Ungültiger Dateityp. Bitte eine .ini-Datei hochladen.', 'warning')

        field_map = {
            'description': ('description', str),
            'slicer_args': ('slicer_args', str),
            'is_active': ('is_active', bool)
        }
        update_model_from_form(new_profile, request.form, field_map)
        
        printer_ids = request.form.getlist('printers', type=int)
        filament_type_ids = request.form.getlist('filaments', type=int)

        new_profile.printers = Printer.query.filter(Printer.id.in_(printer_ids)).all()
        new_profile.compatible_filaments = FilamentType.query.filter(FilamentType.id.in_(filament_type_ids)).all()

        db.session.add(new_profile)
        db.session.commit()
        flash(f"Slicer-Profil '{name}' erfolgreich erstellt.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Erstellen des Profils: {e}", 'danger')
    
    return redirect(url_for('slicer_profiles_bp.list_profiles'))

@slicer_profiles_bp.route('/edit/<int:profile_id>', methods=['GET', 'POST'])
@login_required
def edit_profile(profile_id):
    profile = db.session.get(SlicerProfile, profile_id)
    if not profile:
        flash("Profil nicht gefunden.", "danger")
        return redirect(url_for('slicer_profiles_bp.list_profiles'))
    
    if request.method == 'POST':
        try:
            if 'profile_file' in request.files:
                file = request.files['profile_file']
                if file and file.filename != '' and allowed_profile_file(file.filename):
                    delete_profile_file(profile.filename)
                    unique_filename = save_profile_file(file)
                    profile.filename = unique_filename
                elif file.filename != '':
                    flash('Ungültiger Dateityp. Bitte eine .ini-Datei hochladen.', 'warning')

            field_map = {
                'name': ('name', str),
                'description': ('description', str),
                'slicer_args': ('slicer_args', str),
                'is_active': ('is_active', bool)
            }
            update_model_from_form(profile, request.form, field_map)
            
            printer_ids = request.form.getlist('printers', type=int)
            filament_type_ids = request.form.getlist('filaments', type=int)
            
            profile.printers = Printer.query.filter(Printer.id.in_(printer_ids)).all()
            profile.compatible_filaments = FilamentType.query.filter(FilamentType.id.in_(filament_type_ids)).all()

            db.session.commit()
            flash(f"Profil '{profile.name}' erfolgreich aktualisiert.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Aktualisieren des Profils: {e}", 'danger')
        return redirect(url_for('slicer_profiles_bp.list_profiles'))

    # GET Request
    profiles = SlicerProfile.query.order_by(SlicerProfile.name).all()
    printers = Printer.query.order_by(Printer.name).all()
    # KORREKTUR: Lädt jetzt auch hier die vollständige Filament-Typ-Liste
    filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    
    return render_template('slicer/profiles.html', 
                           profiles=profiles, 
                           printers=printers,
                           filament_types=filament_types,
                           form_title=f"Profil bearbeiten: {profile.name}", 
                           profile_to_edit=profile)


@slicer_profiles_bp.route('/delete/<int:profile_id>', methods=['POST'])
@login_required
def delete_profile(profile_id):
    profile = db.session.get(SlicerProfile, profile_id)
    if profile:
        try:
            if profile.gcode_files.first():
                flash(f"Profil '{profile.name}' kann nicht gelöscht werden, da es noch von G-Code-Dateien verwendet wird.", "warning")
            else:
                delete_profile_file(profile.filename)
                
                db.session.delete(profile)
                db.session.commit()
                flash(f"Profil '{profile.name}' wurde gelöscht.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Löschen des Profils: {e}", "danger")
    else:
        flash("Profil nicht gefunden.", "danger")
        
    return redirect(url_for('slicer_profiles_bp.list_profiles'))