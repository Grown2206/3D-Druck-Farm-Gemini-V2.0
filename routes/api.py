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
    FilamentType, SystemSetting, GCodeFile, FilamentSpool, LayoutItem,
    TimeWindow, JobDependency, DependencyType, DeadlineStatus
)
from printer_communication import get_printer_status, test_printer_connection
import datetime
from .services import assign_job_to_printer
from sqlalchemy import func, or_
from gcode_analyzer import analyze_gcode, create_gcode_preview
from flask_login import login_required
from validators import DependencyValidator

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




@api_bp.route('/job/<int:job_id>/dependencies', methods=['GET'])
@login_required
def get_dependencies(job_id):
    """
    Liefert alle Abhängigkeiten eines Jobs.
    
    Returns:
        JSON mit Liste der Abhängigkeiten
    """
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'error': 'Job nicht gefunden'}), 404
    
    # Abhängigkeiten (Jobs von denen dieser Job abhängt)
    dependencies = []
    for dep in job.dependencies:
        dependencies.append({
            'id': dep.id,
            'depends_on_job_id': dep.depends_on_job_id,
            'depends_on_job_name': dep.depends_on.name,
            'type': dep.dependency_type.value,
            'status': dep.depends_on.status.value,
            'is_blocking': dep.depends_on.status != JobStatus.COMPLETED if dep.dependency_type == DependencyType.FINISH_TO_START else False
        })
    
    # Dependents (Jobs die von diesem Job abhängen)
    dependents = []
    for dep in job.dependents:
        dependents.append({
            'id': dep.id,
            'dependent_job_id': dep.job_id,
            'dependent_job_name': dep.job.name,
            'type': dep.dependency_type.value,
            'status': dep.job.status.value
        })
    
    return jsonify({
        'job_id': job.id,
        'job_name': job.name,
        'can_start': job.can_start,
        'dependencies': dependencies,
        'dependents': dependents,
        'blocking_count': len(job.get_blocking_dependencies())
    })


@api_bp.route('/job/<int:job_id>/dependencies', methods=['POST'])
@login_required
def add_dependency(job_id):
    """
    Fügt eine neue Abhängigkeit hinzu.
    
    Body:
        depends_on_job_id: int
        type: str (finish_to_start | start_to_start)
    """
    try:
        data = request.get_json()
        depends_on_id = data.get('depends_on_job_id')
        dep_type = data.get('type', 'finish_to_start').upper()
        
        if not depends_on_id:
            return jsonify({'error': 'depends_on_job_id fehlt'}), 400
        
        # Validierung
        is_valid, message = DependencyValidator.validate_dependency(
            job_id, depends_on_id, db.session
        )
        
        if not is_valid:
            return jsonify({'error': message}), 400
        
        # Erstelle Abhängigkeit
        try:
            dependency_type = DependencyType[dep_type]
        except KeyError:
            return jsonify({'error': f'Ungültiger Typ: {dep_type}'}), 400
        
        dependency = JobDependency(
            job_id=job_id,
            depends_on_job_id=depends_on_id,
            dependency_type=dependency_type
        )
        
        db.session.add(dependency)
        db.session.commit()
        
        # Aktualisiere Prioritäten
        job = db.session.get(Job, job_id)
        if job.project:
            from validators import CriticalPathCalculator, PriorityCalculator
            CriticalPathCalculator.calculate(job.project)
            job.priority_score = PriorityCalculator.calculate_priority_score(job)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Abhängigkeit erfolgreich erstellt',
            'dependency_id': dependency.id
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dependency/<int:dep_id>', methods=['DELETE'])
@login_required
def delete_dependency(dep_id):
    """Löscht eine Abhängigkeit"""
    try:
        dependency = db.session.get(JobDependency, dep_id)
        if not dependency:
            return jsonify({'error': 'Abhängigkeit nicht gefunden'}), 404
        
        job_id = dependency.job_id
        db.session.delete(dependency)
        db.session.commit()
        
        # Aktualisiere Prioritäten
        job = db.session.get(Job, job_id)
        if job and job.project:
            from validators import CriticalPathCalculator, PriorityCalculator
            CriticalPathCalculator.calculate(job.project)
            job.priority_score = PriorityCalculator.calculate_priority_score(job)
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'Abhängigkeit gelöscht'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/job/<int:job_id>/dependency_graph', methods=['GET'])
@login_required
def get_dependency_graph(job_id):
    """
    Liefert Abhängigkeitsgraph für Visualisierung.
    Format kompatibel mit vis.js oder D3.js
    """
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({'error': 'Job nicht gefunden'}), 404
    
    # Sammle alle verbundenen Jobs
    all_deps = job.get_all_dependencies()
    
    nodes = []
    edges = []
    
    for j in all_deps:
        nodes.append({
            'id': j.id,
            'label': j.name,
            'status': j.status.value,
            'is_critical': j.is_on_critical_path,
            'priority_score': j.priority_score
        })
        
        for dep in j.dependencies:
            if dep.depends_on in all_deps:
                edges.append({
                    'from': dep.depends_on_job_id,
                    'to': j.id,
                    'type': dep.dependency_type.value
                })
    
    return jsonify({
        'nodes': nodes,
        'edges': edges
    })


# ==================== ZEITFENSTER-MANAGEMENT ====================

@api_bp.route('/printer/<int:printer_id>/time_windows', methods=['GET'])
@login_required
def get_time_windows(printer_id):
    """Liefert alle Zeitfenster eines Druckers"""
    printer = db.session.get(Printer, printer_id)
    if not printer:
        return jsonify({'error': 'Drucker nicht gefunden'}), 404
    
    windows = []
    for window in printer.time_windows:
        windows.append({
            'id': window.id,
            'day_of_week': window.day_of_week,
            'weekday_name': window.weekday_name,
            'start_time': window.start_time.strftime('%H:%M'),
            'end_time': window.end_time.strftime('%H:%M'),
            'is_active': window.is_active,
            'description': window.description
        })
    
    return jsonify({
        'printer_id': printer.id,
        'printer_name': printer.name,
        'time_windows': windows,
        'currently_available': printer.is_available_at()
    })


@api_bp.route('/printer/<int:printer_id>/time_windows', methods=['POST'])
@login_required
def add_time_window(printer_id):
    """
    Fügt ein neues Zeitfenster hinzu.
    
    Body:
        day_of_week: int (0-6)
        start_time: str (HH:MM)
        end_time: str (HH:MM)
        description: str (optional)
    """
    try:
        printer = db.session.get(Printer, printer_id)
        if not printer:
            return jsonify({'error': 'Drucker nicht gefunden'}), 404
        
        data = request.get_json()
        
        day = data.get('day_of_week')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')
        description = data.get('description', '')
        
        # Validierung
        if day is None or not start_time_str or not end_time_str:
            return jsonify({'error': 'day_of_week, start_time und end_time erforderlich'}), 400
        
        if not (0 <= day <= 6):
            return jsonify({'error': 'day_of_week muss zwischen 0 und 6 liegen'}), 400
        
        # Parse Zeiten
        start_time = datetime.datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.datetime.strptime(end_time_str, '%H:%M').time()
        
        if start_time >= end_time:
            return jsonify({'error': 'start_time muss vor end_time liegen'}), 400
        
        # Erstelle Zeitfenster
        window = TimeWindow(
            printer_id=printer.id,
            day_of_week=day,
            start_time=start_time,
            end_time=end_time,
            is_active=True,
            description=description
        )
        
        db.session.add(window)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Zeitfenster erstellt',
            'window_id': window.id
        })
    
    except ValueError as e:
        return jsonify({'error': f'Ungültiges Zeitformat: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/time_window/<int:window_id>', methods=['PUT'])
@login_required
def update_time_window(window_id):
    """Aktualisiert ein Zeitfenster"""
    try:
        window = db.session.get(TimeWindow, window_id)
        if not window:
            return jsonify({'error': 'Zeitfenster nicht gefunden'}), 404
        
        data = request.get_json()
        
        if 'day_of_week' in data:
            day = data['day_of_week']
            if not (0 <= day <= 6):
                return jsonify({'error': 'Ungültiger Wochentag'}), 400
            window.day_of_week = day
        
        if 'start_time' in data:
            window.start_time = datetime.datetime.strptime(data['start_time'], '%H:%M').time()
        
        if 'end_time' in data:
            window.end_time = datetime.datetime.strptime(data['end_time'], '%H:%M').time()
        
        if 'is_active' in data:
            window.is_active = bool(data['is_active'])
        
        if 'description' in data:
            window.description = data['description']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Zeitfenster aktualisiert'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/time_window/<int:window_id>', methods=['DELETE'])
@login_required
def delete_time_window(window_id):
    """Löscht ein Zeitfenster"""
    try:
        window = db.session.get(TimeWindow, window_id)
        if not window:
            return jsonify({'error': 'Zeitfenster nicht gefunden'}), 404
        
        db.session.delete(window)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Zeitfenster gelöscht'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/printer/<int:printer_id>/availability_check', methods=['POST'])
@login_required
def check_printer_availability(printer_id):
    """
    Prüft Verfügbarkeit eines Druckers zu einer bestimmten Zeit.
    
    Body:
        check_time: str (ISO format) (optional, default: now)
    """
    printer = db.session.get(Printer, printer_id)
    if not printer:
        return jsonify({'error': 'Drucker nicht gefunden'}), 404
    
    data = request.get_json() or {}
    
    check_time = datetime.datetime.utcnow()
    if 'check_time' in data:
        try:
            check_time = datetime.datetime.fromisoformat(data['check_time'])
        except ValueError:
            return jsonify({'error': 'Ungültiges Zeitformat'}), 400
    
    is_available = printer.is_available_at(check_time)
    next_available = None
    
    if not is_available:
        next_available = printer.get_next_available_time()
    
    return jsonify({
        'printer_id': printer.id,
        'printer_name': printer.name,
        'check_time': check_time.isoformat(),
        'is_available': is_available,
        'next_available': next_available.isoformat() if next_available else None,
        'has_time_windows': len(printer.time_windows) > 0
    })


# ==================== KALENDER-API ====================

@api_bp.route('/jobs/calendar', methods=['GET'])
@login_required
def jobs_calendar():
    """
    Liefert Jobs für Kalender-Ansicht im FullCalendar-Format.
    
    Query-Parameter:
        start: ISO datetime
        end: ISO datetime
    """
    try:
        # Filter für Datum-Range (von FullCalendar übergeben)
        start_str = request.args.get('start')
        end_str = request.args.get('end')
        
        query = Job.query.filter(
            Job.status.in_([
                JobStatus.ASSIGNED, JobStatus.QUEUED, 
                JobStatus.PRINTING, JobStatus.COMPLETED
            ])
        )
        
        if start_str:
            start_date = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            query = query.filter(
                db.or_(
                    Job.estimated_start_time >= start_date,
                    Job.start_time >= start_date
                )
            )
        
        if end_str:
            end_date = datetime.datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            query = query.filter(
                db.or_(
                    Job.estimated_end_time <= end_date,
                    Job.end_time <= end_date
                )
            )
        
        jobs = query.limit(500).all()  # Limit für Performance
        
        events = []
        for job in jobs:
            # Bestimme Start/End-Zeit
            if job.status == JobStatus.COMPLETED:
                start = job.start_time or job.created_at
                end = job.end_time or job.completed_at or start
            else:
                start = job.estimated_start_time or job.created_at
                end = job.estimated_end_time or (start + datetime.timedelta(hours=1))
            
            # Farbe basierend auf Status und Priorität
            if job.is_on_critical_path:
                color = '#dc3545'
            elif job.deadline_status == DeadlineStatus.RED:
                color = '#ff6384'
            elif job.deadline_status == DeadlineStatus.OVERDUE:
                color = '#8b0000'
            elif job.status == JobStatus.PRINTING:
                color = '#198754'
            elif job.status == JobStatus.COMPLETED:
                color = '#6c757d'
            else:
                color = '#0d6efd'
            
            event = {
                'id': job.id,
                'title': job.name,
                'start': start.isoformat(),
                'end': end.isoformat(),
                'color': color,
                'extendedProps': {
                    'printer_name': job.assigned_printer.name if job.assigned_printer else None,
                    'status': job.status.value,
                    'priority_score': job.priority_score,
                    'deadline_status': job.deadline_status.value if job.deadline_status else None,
                    'is_critical': job.is_on_critical_path,
                    'project_name': job.project.name if job.project else None
                }
            }
            
            events.append(event)
        
        return jsonify(events)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
