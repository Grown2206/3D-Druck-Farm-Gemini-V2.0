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
    profile = db.session.get(SlicerProfile, profile_id)
    if not profile:
        return False, "Ausgewähltes Slicer-Profil nicht gefunden.", None
    
    if not profile.filename:
        return False, f"Slicer-Profil '{profile.name}' hat keine .ini-Datei zugewiesen.", None

    slicer_path = os.environ.get('PRUSA_SLICER_PATH')
    slicer_datadir = os.environ.get('PRUSA_SLICER_DATADIR')

    if not slicer_path or not os.path.exists(slicer_path):
        return False, "PrusaSlicer-Pfad ist nicht in .env konfiguriert oder ungültig.", None
    
    if not slicer_datadir or not os.path.exists(slicer_datadir):
        return False, "PrusaSlicer-Datenverzeichnis (DATADIR) ist nicht in .env konfiguriert oder ungültig.", None


    stl_full_path = os.path.join(current_app.config['STL_FOLDER'], stl_filename)
    base_filename = stl_filename.replace('.stl', f'_{profile.name.replace(" ", "_")}.gcode')
    gcode_filename = secure_filename(base_filename)
    gcode_full_path = os.path.join(current_app.config['GCODE_FOLDER'], gcode_filename)
    profile_full_path = os.path.join(current_app.config['SLICER_PROFILES_FOLDER'], profile.filename)

    command = [
        slicer_path,
        "--datadir", slicer_datadir,
        "--export-gcode",
        "-o", gcode_full_path,
        "--load", profile_full_path,
        stl_full_path
    ]

    print(f"Executing PrusaSlicer command: {' '.join(command)}")

    try:
        process = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8')
        if process.returncode != 0:
            if not os.path.exists(gcode_full_path) or os.path.getsize(gcode_full_path) == 0:
                error_message = f"PrusaSlicer Fehler (Exit Code {process.returncode}):\nSTDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
                print(error_message)
                return False, "Fehler im PrusaSlicer-Prozess. Details im Server-Log.", None
    
        if not os.path.exists(gcode_full_path) or os.path.getsize(gcode_full_path) < 100:
            return False, "Slicing-Prozess lief ohne Fehler durch, hat aber keine gültige G-Code-Datei erstellt.", None

    except FileNotFoundError:
        return False, f"Slicer-Programm unter '{slicer_path}' nicht gefunden.", None
    except Exception as e:
        return False, f"Ein unerwarteter Fehler ist während des Slicing-Prozesses aufgetreten: {e}", None
    
    analysis_results = analyze_gcode(gcode_full_path)
    if not analysis_results:
        return False, "Analyse der erstellten G-Code-Datei fehlgeschlagen.", None

    preview_filename = gcode_filename.replace('.gcode', '.png')
    preview_full_path = os.path.join(current_app.config['GCODE_FOLDER'], preview_filename)
    
    preview_created = create_gcode_preview(gcode_full_path, preview_full_path)
    final_preview_filename = preview_filename if preview_created else None
    if not preview_created:
        print(f"Warnung: Konnte keine G-Code-Vorschau für {gcode_filename} erstellen.")


    new_gcode_file = GCodeFile(
        filename=gcode_filename,
        source_stl_filename=stl_filename,
        slicer_profile_id=profile_id,
        estimated_print_time_min=analysis_results.get('print_time_min'),
        material_needed_g=analysis_results.get('filament_used_g'),
        filament_needed_mm=analysis_results.get('filament_used_mm'),
        tool_changes=analysis_results.get('tool_changes'),
        preview_image_filename=final_preview_filename,
        layer_count=analysis_results.get('layer_count'),
        dimensions_x_mm=analysis_results.get('width_mm'),
        dimensions_y_mm=analysis_results.get('depth_mm'),
        filament_per_tool=json.dumps(analysis_results.get('filament_per_tool', {}))
    )
    db.session.add(new_gcode_file)
    db.session.commit()
    
    return True, f"Modell '{stl_filename}' erfolgreich mit Profil '{profile.name}' gesliced.", new_gcode_file
