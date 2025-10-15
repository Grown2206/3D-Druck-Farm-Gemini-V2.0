# /routes/slicer.py
import os
import secrets
import subprocess
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from extensions import db
from models import GCodeFile, SlicerProfile, Printer, FilamentType
from flask_login import login_required
from gcode_analyzer import analyze_gcode, create_gcode_preview
from sqlalchemy import distinct
from .forms import SlicerForm

slicer_bp = Blueprint('slicer_bp', __name__)

def allowed_stl_file(filename):
    """Überprüft, ob die hochgeladene Datei eine .stl-Datei ist."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'stl'}

@slicer_bp.route('/', methods=['GET'])
@login_required
def slicer_index():
    """Zeigt die Slicer-Hauptseite mit dem Upload-Formular an."""
    form = SlicerForm()
    
    # Dynamisches Befüllen der Auswahlfelder für die Anzeige
    form.printer_id.choices = [('', '-- Drucker wählen --')] + [(p.id, p.name) for p in Printer.query.order_by(Printer.name).all()]
    
    material_types = [m[0] for m in db.session.query(distinct(FilamentType.material_type)).order_by(FilamentType.material_type).all()]
    form.material_type.choices = [('', '-- Materialtyp wählen --')] + [(m, m) for m in material_types]
    
    form.slicer_profile_id.choices = [('', '-- Zuerst filtern --')]

    gcode_files = GCodeFile.query.order_by(GCodeFile.created_at.desc()).all()
    
    return render_template('slicer/index.html', 
                           form=form,
                           gcode_files=gcode_files)

@slicer_bp.route('/slice', methods=['POST'])
@login_required
def slice_file():
    """Verarbeitet die Formular-Daten und startet den Slicing-Prozess."""
    form = SlicerForm()
    
    # KORREKTUR: Choices müssen VOR der Validierung exakt neu befüllt werden.
    form.printer_id.choices = [(p.id, p.name) for p in Printer.query.order_by(Printer.name).all()]
    
    # HIER WAR DER FEHLER: Die Tupel aus der DB-Abfrage wurden nicht korrekt entpackt.
    material_types_query = db.session.query(distinct(FilamentType.material_type)).order_by(FilamentType.material_type).all()
    form.material_type.choices = [(m[0], m[0]) for m in material_types_query]
    
    # Profile müssen ebenfalls befüllt werden für die Validierung
    form.slicer_profile_id.choices = [(p.id, p.name) for p in SlicerProfile.query.all()]

    if form.validate_on_submit():
        file = form.stl_file.data
        profile_id = form.slicer_profile_id.data

        # Die allowed_stl_file-Prüfung ist durch FileAllowed im Formular bereits abgedeckt,
        # aber eine doppelte Prüfung schadet nicht.
        if file:
            try:
                filename = secure_filename(file.filename)
                unique_stl_filename = f"{secrets.token_hex(8)}_{filename}"
                stl_full_path = os.path.join(current_app.config['STL_FOLDER'], unique_stl_filename)
                file.save(stl_full_path)

                success, message, _ = run_slicing_process(unique_stl_filename, int(profile_id))
                
                if success:
                    flash(message, 'success')
                else:
                    flash(message, 'danger')

            except Exception as e:
                flash(f'Ein unerwarteter Fehler ist aufgetreten: {e}', 'danger')
    else:
        # Fehlermeldungen aus dem Formular präzise anzeigen
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Fehler im Feld '{getattr(form, field).label.text}': {error}", 'danger')

    return redirect(url_for('slicer_bp.slicer_index'))


@slicer_bp.route('/delete/<int:gcode_file_id>', methods=['POST'])
@login_required
def delete_gcode(gcode_file_id):
    gcode_file = db.session.get(GCodeFile, gcode_file_id)
    if not gcode_file:
        flash('G-Code-Datei nicht gefunden.', 'danger')
        return redirect(url_for('slicer_bp.slicer_index'))

    try:
        if gcode_file.filename:
            gcode_path = os.path.join(current_app.config['GCODE_FOLDER'], gcode_file.filename)
            if os.path.exists(gcode_path): os.remove(gcode_path)
        if gcode_file.source_stl_filename:
            stl_path = os.path.join(current_app.config['STL_FOLDER'], gcode_file.source_stl_filename)
            if os.path.exists(stl_path): os.remove(stl_path)
        if gcode_file.preview_image_filename:
            preview_path = os.path.join(current_app.config['GCODE_FOLDER'], gcode_file.preview_image_filename)
            if os.path.exists(preview_path): os.remove(preview_path)

        db.session.delete(gcode_file)
        db.session.commit()
        flash('G-Code-Datei und zugehörige Dateien erfolgreich gelöscht.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ein unerwarteter Fehler ist aufgetreten: {e}', 'danger')

    return redirect(url_for('slicer_bp.slicer_index'))


def run_slicing_process(stl_filename, profile_id):
    """Führt den Slicing-Prozess mit PrusaSlicer durch."""
    profile = db.session.get(SlicerProfile, profile_id)
    if not profile:
        return False, "Ausgewähltes Slicer-Profil nicht gefunden.", None
    
    if not profile.filename:
        return False, f"Slicer-Profil '{profile.name}' hat keine .ini-Datei zugewiesen.", None

    slicer_path = os.environ.get('PRUSA_SLICER_PATH')
    slicer_datadir = os.environ.get('PRUSA_SLICER_DATADIR')

    # FIX: String war nicht geschlossen
    if not slicer_path or not os.path.exists(slicer_path):
        return False, "PrusaSlicer-Pfad ist nicht in .env konfiguriert oder ungültig.", None
    
    # Weitere Validierung
    if not slicer_datadir or not os.path.exists(slicer_datadir):
        return False, "PrusaSlicer-Datenverzeichnis ist nicht in .env konfiguriert oder ungültig.", None
    
    try:
        # STL-Pfad konstruieren
        stl_full_path = os.path.join(current_app.config['STL_FOLDER'], stl_filename)
        
        if not os.path.exists(stl_full_path):
            return False, f"STL-Datei '{stl_filename}' wurde nicht gefunden.", None
        
        # G-Code-Ausgabepfad
        gcode_filename = f"{os.path.splitext(stl_filename)[0]}.gcode"
        gcode_full_path = os.path.join(current_app.config['GCODE_FOLDER'], gcode_filename)
        
        # Profil-Pfad
        profile_path = os.path.join(current_app.config['SLICER_PROFILES_FOLDER'], profile.filename)
        
        if not os.path.exists(profile_path):
            return False, f"Profil-Datei '{profile.filename}' wurde nicht gefunden.", None
        
        # PrusaSlicer-Befehl ausführen
        command = [
            slicer_path,
            '--load', profile_path,
            '--datadir', slicer_datadir,
            '--export-gcode',
            '--output', gcode_full_path,
            stl_full_path
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300  # 5 Minuten Timeout
        )
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else "Unbekannter Slicing-Fehler"
            return False, f"Slicing fehlgeschlagen: {error_msg}", None
        
        # Prüfe ob G-Code-Datei erstellt wurde
        if not os.path.exists(gcode_full_path):
            return False, "G-Code-Datei wurde nicht erstellt.", None
        
        # Analysiere G-Code
        from gcode_analyzer import analyze_gcode, create_gcode_preview
        
        gcode_info = analyze_gcode(gcode_full_path)
        
        # Erstelle Vorschau
        preview_filename = f"{os.path.splitext(gcode_filename)[0]}_preview.png"
        preview_path = os.path.join(current_app.config['GCODE_FOLDER'], preview_filename)
        create_gcode_preview(gcode_full_path, preview_path)
        
        # Speichere G-Code in Datenbank
        # WICHTIG: Verwende die korrekten Feldnamen aus models.py
        gcode_file = GCodeFile(
            filename=gcode_filename,
            source_stl_filename=stl_filename,
            slicer_profile_id=profile.id,
            estimated_print_time_min=gcode_info.get('print_time_min'),
            material_needed_g=gcode_info.get('filament_used_g'),
            layer_count=gcode_info.get('layer_count'),
            dimensions_x_mm=gcode_info.get('width_mm'),  # X-Dimension
            dimensions_y_mm=gcode_info.get('depth_mm'),  # Y-Dimension
            dimensions_z_mm=gcode_info.get('height_mm'),  # ✅ NEU
            preview_image_filename=preview_filename if os.path.exists(preview_path) else None
        )
        
        db.session.add(gcode_file)
        db.session.commit()
        
        return True, f"Slicing erfolgreich abgeschlossen. G-Code: {gcode_filename}", gcode_file.id
        
    except subprocess.TimeoutExpired:
        return False, "Slicing-Prozess hat das Zeitlimit überschritten.", None
    except Exception as e:
        return False, f"Fehler beim Slicing: {str(e)}", None