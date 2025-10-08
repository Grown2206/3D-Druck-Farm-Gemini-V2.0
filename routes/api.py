# /routes/api.py
import os
import secrets
import subprocess
from flask import Blueprint, jsonify, request, url_for, current_app
from flask_login import login_required
from extensions import db, socketio
from models import (
    Printer, Job, JobStatus, JobQuality, PrintSnapshot, PrinterStatus,
    PrinterStatusLog, ToDo, ToDoCategory, ToDoStatus, SlicerProfile,
    FilamentType, SystemSetting, GCodeFile, FilamentSpool, LayoutItem
)
from printer_communication import get_printer_status, test_printer_connection
import datetime
from .services import assign_job_to_printer
from sqlalchemy import func, or_
from gcode_analyzer import analyze_gcode, create_gcode_preview

api_bp = Blueprint('api_bp', __name__, url_prefix='/api')

# --- Drucker-Interaktionen ---

@api_bp.route('/printer/<int:printer_id>/test', methods=['POST'])
@login_required
def test_connection(printer_id):
    """Testet die Netzwerkverbindung zu einem Drucker."""
    printer = db.session.get(Printer, printer_id)
    if not printer:
        return jsonify({'status': 'error', 'message': 'Drucker nicht gefunden.'}), 404
    
    success, message = test_printer_connection(printer)
    
    if success:
        return jsonify({'status': 'success', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': message})

@api_bp.route('/printer/<int:printer_id>/status', methods=['POST'])
@login_required
def set_printer_status(printer_id):
    """Setzt manuell den Status eines Druckers."""
    printer = db.session.get(Printer, printer_id)
    if not printer:
        return jsonify({'status': 'error', 'message': 'Drucker nicht gefunden.'}), 404
    
    data = request.get_json()
    new_status_str = data.get('status')

    if not new_status_str:
        return jsonify({'status': 'error', 'message': 'Kein Status übermittelt.'}), 400

    try:
        new_status = PrinterStatus[new_status_str]
        printer.status = new_status
        log_entry = PrinterStatusLog(printer_id=printer.id, status=new_status)
        db.session.add(log_entry)
        db.session.commit()
        
        socketio.emit('status_update', get_all_statuses().get_json())
        
        return jsonify({'status': 'success', 'message': f"Status für {printer.name} auf '{new_status.value}' gesetzt."})
    except (KeyError, ValueError):
        return jsonify({'status': 'error', 'message': 'Ungültiger Statuswert.'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Fehler: {e}'}), 500

# --- Dashboard & Slicer ---

@api_bp.route('/dashboard/status')
@login_required
def get_all_statuses():
    """Gibt den kombinierten Status aller Drucker für das Dashboard zurück."""
    printers = Printer.query.all()
    status_data = {}
    for printer in printers:
        primary_job = printer.get_active_or_next_job()
        next_job_display = None
        if primary_job and primary_job.status == JobStatus.PRINTING:
            next_job_display = printer.jobs.filter(
                Job.status.in_([JobStatus.QUEUED, JobStatus.ASSIGNED])
            ).order_by(Job.priority.desc(), Job.created_at.asc()).first()

        time_info = {'elapsed': 0, 'total': 0}
        progress = 0
        
        if primary_job:
            time_info = primary_job.get_elapsed_and_total_time_seconds()
            progress = primary_job.get_manual_progress()

        current_spool_data = None
        current_spool = printer.assigned_spools.filter_by(is_in_use=True).first()
        if current_spool:
            current_spool_data = {
                "short_id": current_spool.short_id,
                "name": f"{current_spool.filament_type.name} ({current_spool.filament_type.material_type})",
                "color_hex": current_spool.filament_type.color_hex
            }
        
        next_job_data = None
        if next_job_display:
             next_job_data = {
                 "name": next_job_display.name,
                 "material": f"{next_job_display.required_filament_type.name} ({next_job_display.required_filament_type.material_type})" if next_job_display.required_filament_type else "Nicht spezifiziert"
             }

        status_data[printer.id] = {
            'id': printer.id, 'name': printer.name, 'state': printer.status.value, 'state_key': printer.status.name,
            'job_id': primary_job.id if primary_job else None, 'job_name': primary_job.name if primary_job else None,
            'progress': progress, 'time_info': time_info,
            'preview_image_url': primary_job.gcode_file.preview_image_url if (primary_job and primary_job.gcode_file) else None,
            'current_spool': current_spool_data, 'next_job': next_job_data,
            'gcode_file_id': primary_job.gcode_file_id if (primary_job and primary_job.gcode_file) else None
        }
    return jsonify(status_data)


@api_bp.route('/slicer/profiles/filter', methods=['POST'])
@login_required
def filter_slicer_profiles():
    data = request.get_json()
    if data is None: return jsonify({'error': 'Invalid JSON'}), 400
    
    printer_id_str = data.get('printer_id')
    filament_type_id_str = data.get('filament_type_id')
    
    query = SlicerProfile.query.filter_by(is_active=True)
    
    if printer_id_str:
        try:
            query = query.filter(SlicerProfile.printers.any(id=int(printer_id_str)))
        except (ValueError, TypeError): pass
    
    if filament_type_id_str:
        try:
            query = query.filter(SlicerProfile.compatible_filaments.any(id=int(filament_type_id_str)))
        except (ValueError, TypeError): pass
            
    profiles = query.order_by(SlicerProfile.name).all()
    return jsonify([{'id': p.id, 'name': p.name} for p in profiles])

# --- Batch Planner ---
@api_bp.route('/batch-planner/jobs', methods=['GET'])
@login_required
def get_batch_planner_jobs():
    printer_id = request.args.get('printer_id', type=int)
    filament_type_id = request.args.get('filament_type_id', type=int)
    if not printer_id or not filament_type_id:
        return jsonify({'error': 'Drucker- und Material-ID sind erforderlich'}), 400
    query = Job.query.filter(
        Job.status == JobStatus.PENDING,
        Job.is_archived == False,
        Job.required_filament_type_id == filament_type_id,
        Job.source_stl_filename.isnot(None)
    )
    jobs = query.order_by(Job.priority.desc(), Job.created_at.asc()).all()
    job_data = [{
        'id': job.id,
        'name': job.name,
        'priority': job.priority,
        'created_at': job.created_at.strftime('%d.%m.%Y'),
        'gcode_file': job.gcode_file.filename if job.gcode_file else 'N/A'
    } for job in jobs]
    return jsonify(job_data)


@api_bp.route('/batch-planner/nest', methods=['POST'])
@login_required
def nest_and_slice():
    """Nimmt Job-IDs, ordnet die STLs an und sliced sie zu einem G-Code."""
    data = request.get_json()
    job_ids = data.get('job_ids')
    printer_id = data.get('printer_id')
    profile_id = data.get('profile_id')

    if not all([job_ids, printer_id, profile_id]):
        return jsonify({'status': 'error', 'message': 'Fehlende Daten: Job-IDs, Drucker-ID und Profil-ID sind erforderlich.'}), 400

    jobs = Job.query.filter(Job.id.in_(job_ids)).all()
    profile = db.session.get(SlicerProfile, profile_id)
    printer = db.session.get(Printer, printer_id)
    
    if not profile or not profile.filename:
        return jsonify({'status': 'error', 'message': 'Slicer-Profil ist ungültig.'}), 400
    if not printer:
        return jsonify({'status': 'error', 'message': 'Drucker nicht gefunden.'}), 404

    stl_paths = [os.path.join(current_app.config['STL_FOLDER'], job.source_stl_filename) for job in jobs if job.source_stl_filename and os.path.exists(os.path.join(current_app.config['STL_FOLDER'], job.source_stl_filename))]
    if not stl_paths:
        return jsonify({'status': 'error', 'message': 'Keine gültigen STL-Dateien gefunden.'}), 400

    slicer_path = os.environ.get('PRUSA_SLICER_PATH')
    slicer_datadir = os.environ.get('PRUSA_SLICER_DATADIR')
    if not all([slicer_path, slicer_datadir, os.path.exists(slicer_path), os.path.exists(slicer_datadir)]):
        return jsonify({'status': 'error', 'message': 'Slicer-Pfade sind nicht korrekt konfiguriert.'}), 500

    batch_name = f"batch_{secrets.token_hex(8)}.gcode"
    gcode_full_path = os.path.join(current_app.config['GCODE_FOLDER'], batch_name)
    profile_full_path = os.path.join(current_app.config['SLICER_PROFILES_FOLDER'], profile.filename)

    command = [
        f'"{slicer_path}"',
        "--datadir", f'"{slicer_datadir}"',
        "--load", f'"{profile_full_path}"',
        "--export-gcode",
        "-o", f'"{gcode_full_path}"',
    ] + [f'"{path}"' for path in stl_paths]

    try:
        final_command_str = " ".join(command)
        process = subprocess.run(final_command_str, capture_output=True, text=True, check=True, encoding='utf-8', shell=True)
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout
        full_command = " ".join(command)
        error_message = f"Slicer-Fehler: Der Befehl ist fehlgeschlagen.\nBefehl: {full_command}\nAusgabe: {error_output}"
        print(error_message)
        return jsonify({'status': 'error', 'message': "Slicer-Fehler: Details siehe Server-Log."}), 500
    
    if not os.path.exists(gcode_full_path) or os.path.getsize(gcode_full_path) == 0:
        return jsonify({'status': 'error', 'message': 'Slicing hat keine G-Code-Datei erstellt. Prüfen Sie die Kompatibilität.'}), 500

    analysis = analyze_gcode(gcode_full_path)
    preview_filename = batch_name.replace('.gcode', '.png')
    preview_path = os.path.join(current_app.config['GCODE_FOLDER'], preview_filename)
    create_gcode_preview(gcode_full_path, preview_path)

    return jsonify({
        'status': 'success',
        'preview_url': url_for('static', filename=f'uploads/gcode/{preview_filename}', _external=True),
        'estimated_time_min': analysis.get('print_time_min'),
        'material_needed_g': analysis.get('filament_used_g'),
        'new_gcode_filename': batch_name
    })

# --- Job-Review ---

@api_bp.route('/job/<int:job_id>/review', methods=['POST'])
@login_required
def review_job(job_id):
    job = db.session.get(Job, job_id)
    if not job: return jsonify({'status': 'error', 'message': 'Auftrag nicht gefunden'}), 404
    try:
        quality_name = request.json.get('quality')
        # ##### HIER IST DIE KORREKTUR #####
        # Greife auf das Enum-Mitglied über seinen Namen zu, nicht über seinen Wert.
        job.quality_assessment = JobQuality[quality_name]
        
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Auftragsbewertung gespeichert.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api_bp.route('/snapshot/<int:snapshot_id>/label', methods=['POST'])
@login_required
def label_snapshot(snapshot_id):
    snapshot = db.session.get(PrintSnapshot, snapshot_id)
    if not snapshot: return jsonify({'status': 'error', 'message': 'Snapshot nicht gefunden'}), 404
    is_failure = request.json.get('is_failure')
    if is_failure is None: return jsonify({'status': 'error', 'message': 'Fehlende Information'}), 400
    try:
        snapshot.is_failure = bool(is_failure)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Snapshot-Label aktualisiert.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ... (Rest der Datei bleibt unverändert) ...

# --- Scheduler Einstellungen ---

@api_bp.route('/settings/scheduler/status', methods=['GET'])
@login_required
def get_scheduler_status():
    """Ruft den aktuellen Status des Schedulers ab."""
    setting = SystemSetting.query.filter_by(key='scheduler_enabled').first()
    return jsonify({'enabled': setting.value == 'true' if setting else True})

@api_bp.route('/settings/scheduler/status', methods=['POST'])
@login_required
def set_scheduler_status():
    """Aktiviert oder deaktiviert den Scheduler."""
    is_enabled = request.json.get('enabled')
    if is_enabled is None:
        return jsonify({'status': 'error', 'message': 'Ungültige Anfrage'}), 400
    
    setting = SystemSetting.query.filter_by(key='scheduler_enabled').first()
    if not setting:
        db.session.add(SystemSetting(key='scheduler_enabled', value=str(is_enabled).lower()))
    else:
        setting.value = str(is_enabled).lower()
        
    try:
        db.session.commit()
        message = f'Scheduler {"aktiviert" if is_enabled else "deaktiviert"}.'
        socketio.emit('show_toast', {'message': message, 'category': 'success'})
        return jsonify({'status': 'success', 'message': message})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@api_bp.route('/job/<int:job_id>/preflight_check')
@login_required
def job_preflight_check(job_id):
    """
    Überprüft vor dem Job-Start, ob das richtige Filament geladen ist.
    """
    job = db.session.get(Job, job_id)
    if not job or not job.assigned_printer:
        return jsonify({'status': 'error', 'message': 'Job oder Drucker nicht gefunden.'}), 404

    printer = job.assigned_printer
    required_filament_type = job.required_filament_type
    loaded_spool = printer.assigned_spools.filter_by(is_in_use=True).first()

    if required_filament_type:
        if not loaded_spool:
            return jsonify({
                'status': 'warning', 'match': False,
                'message': f"Für den Auftrag wird '{required_filament_type.name}' benötigt, aber am Drucker '{printer.name}' ist keine Spule geladen."
            })
        
        if loaded_spool.filament_type_id != required_filament_type.id:
            return jsonify({
                'status': 'warning', 'match': False,
                'message': f"Falsches Material! Auftrag erfordert '{required_filament_type.name}', aber '{loaded_spool.filament_type.name}' ist geladen. Trotzdem starten?"
            })

    return jsonify({'status': 'success', 'match': True})



@api_bp.route('/layout')
@login_required
def get_layout():
    """Gibt alle SICHTBAREN Layout-Objekte für die 3D-Szene zurück."""
    layout_items = LayoutItem.query.filter_by(is_visible=True).all()
    
    scene_data = []
    for item in layout_items:
        scene_data.append({
            'id': item.id,
            'name': item.name,
            'item_type': item.item_type.name,
            # ##### HIER IST DIE KORREKTUR #####
            # Erstellt den korrekten Pfad zum 'models'-Ordner.
            'model_path': url_for('static', filename=f'models/{item.model_path}'),
            'position': {'x': item.position_x, 'y': item.position_y, 'z': item.position_z},
            'rotation': {'x': item.rotation_x, 'y': item.rotation_y, 'z': item.rotation_z},
            'scale': {'x': item.scale_x, 'y': item.scale_y, 'z': item.scale_z},
            'color': item.color,
            'printer_id': item.printer_id
        })
            
    return jsonify(scene_data)