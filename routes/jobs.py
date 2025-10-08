# /routes/jobs.py
import io
import csv
from flask import Response
import codecs
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from extensions import db
from models import Job, Printer, GCodeFile, FilamentType, JobStatus, JobQuality, PrinterStatus, PrintSnapshot, FilamentSpool
from flask_login import login_required
from .forms import update_model_from_form
import os

jobs_bp = Blueprint('jobs_bp', __name__, url_prefix='/jobs')

@jobs_bp.route('/dashboard')
@login_required
def dashboard():
    printers = Printer.query.order_by(Printer.name).all()
    unassigned_jobs = Job.query.filter(
        Job.status == JobStatus.PENDING,
        Job.is_archived == False
    ).order_by(Job.priority.desc(), Job.created_at.asc()).all()
    
    available_spools = FilamentSpool.query.filter(
        FilamentSpool.is_in_use == False,
        FilamentSpool.current_weight_g > 0
    ).join(FilamentType).order_by(FilamentType.manufacturer, FilamentType.name).all()
    
    return render_template('index.html',
                           printers=printers,
                           unassigned_jobs=unassigned_jobs,
                           available_spools=available_spools)

@jobs_bp.route('/')
@login_required
def list_jobs():
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '')
    
    sort_by = request.args.get('sort_by', 'created_at')
    direction = request.args.get('direction', 'desc')
    status_filter = request.args.get('status')

    query = Job.query.filter(Job.is_archived == False)

    if status_filter:
        try:
            valid_status = JobStatus[status_filter.upper()]
            query = query.filter(Job.status == valid_status)
        except KeyError:
            flash(f"Ungültiger Filter-Status '{status_filter}' wurde ignoriert.", "warning")
            status_filter = None

    if search_term:
        query = query.filter(Job.name.ilike(f'%{search_term}%'))

    allowed_sort_columns = {
        'name': Job.name, 'status': Job.status, 'priority': Job.priority,
        'created_at': Job.created_at, 'start_time': Job.start_time, 'end_time': Job.end_time
    }
    sort_column = allowed_sort_columns.get(sort_by, Job.created_at)
    sort_expression = sort_column.asc() if direction == 'asc' else sort_column.desc()

    pagination = query.order_by(sort_expression).paginate(page=page, per_page=15, error_out=False)
    jobs = pagination.items
    
    return render_template('jobs/list.html', jobs=jobs, pagination=pagination, current_sort=sort_by, current_direction=direction, current_status=status_filter, search_term=search_term)


@jobs_bp.route('/archive')
@login_required
def archive_list():
    archived_jobs = Job.query.filter(Job.is_archived == True).order_by(Job.end_time.desc()).all()
    return render_template('jobs/archive_list.html', jobs=archived_jobs)

# ##### FIX START: job_details und edit_job zusammengeführt #####
@jobs_bp.route('/<int:job_id>', methods=['GET', 'POST'])
@login_required
def job_details(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        flash('Auftrag nicht gefunden.', 'danger')
        return redirect(url_for('jobs_bp.list_jobs'))
        
    if request.method == 'POST':
        try:
            update_model_from_form(job, request.form, get_job_field_map())
            db.session.commit()
            flash('Auftrag erfolgreich aktualisiert.', 'success')
            # Nach dem Speichern zurück zur Detailansicht (GET-Request)
            return redirect(url_for('jobs_bp.job_details', job_id=job.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Aktualisieren des Auftrags: {e}', 'danger')

    # Logik für GET-Request (Anzeigen der Seite)
    # Wenn der 'edit'-Parameter in der URL ist, wird das Bearbeitungsformular gezeigt
    if 'edit' in request.args:
        gcode_files = GCodeFile.query.order_by(GCodeFile.filename).all()
        filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
        stl_folder = current_app.config['STL_FOLDER']
        available_stls = [f for f in os.listdir(stl_folder) if f.lower().endswith('.stl')] if os.path.exists(stl_folder) else []
        return render_template('jobs/add_edit.html', job=job, gcode_files=gcode_files, 
                               filament_types=filament_types, available_stls=available_stls, 
                               form_title="Auftrag bearbeiten")
    
    # Standardmäßig wird die Detailansicht gezeigt
    return render_template('jobs/details.html', job=job)
# ##### FIX ENDE #####


@jobs_bp.route('/review/<int:job_id>', methods=['GET'])
@login_required
def review_job_page(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        flash('Auftrag nicht gefunden.', 'danger')
        return redirect(url_for('jobs_bp.list_jobs'))
    if job.status != JobStatus.COMPLETED:
        flash('Nur abgeschlossene Aufträge können bewertet werden.', 'warning')
        return redirect(url_for('jobs_bp.job_details', job_id=job.id))
    
    snapshots = job.snapshots.order_by(PrintSnapshot.timestamp.asc()).all()
    return render_template('jobs/review.html', job=job, snapshots=snapshots)


@jobs_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_job():
    if request.method == 'POST':
        try:
            new_job = Job()
            update_model_from_form(new_job, request.form, get_job_field_map())
            db.session.add(new_job)
            db.session.commit()
            flash('Neuer Auftrag erfolgreich erstellt.', 'success')
            return redirect(url_for('jobs_bp.list_jobs'))
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Erstellen des Auftrags: {e}', 'danger')
    
    gcode_files = GCodeFile.query.order_by(GCodeFile.filename).all()
    filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    
    stl_folder = current_app.config['STL_FOLDER']
    available_stls = [f for f in os.listdir(stl_folder) if f.lower().endswith('.stl')] if os.path.exists(stl_folder) else []
    
    return render_template('jobs/add_edit.html', job=None, gcode_files=gcode_files, 
                           filament_types=filament_types, available_stls=available_stls, form_title="Neuen Auftrag erstellen")

# ##### Die alte edit_job Route wird entfernt, da ihre Logik jetzt in job_details ist #####
# @jobs_bp.route('/edit/<int:job_id>', methods=['GET', 'POST'])
# ... (ganze Funktion gelöscht) ...


@jobs_bp.route('/delete/<int:job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    job = db.session.get(Job, job_id)
    if job:
        try:
            db.session.delete(job)
            db.session.commit()
            flash(f'Auftrag "{job.name}" wurde gelöscht.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Löschen: {e}', 'danger')
    return redirect(request.referrer or url_for('jobs_bp.list_jobs'))

@jobs_bp.route('/<int:job_id>/archive', methods=['POST'])
@login_required
def archive_job(job_id):
    job = db.session.get(Job, job_id)
    if job:
        job.is_archived = True
        db.session.commit()
        flash(f'Auftrag "{job.name}" wurde archiviert.', 'success')
    return redirect(url_for('jobs_bp.list_jobs'))

# ... (Rest der Datei bleibt unverändert) ...

@jobs_bp.route('/assign_job', methods=['POST'])
@login_required
def assign_job():
    job_id = request.form.get('job_id')
    printer_id = request.form.get('printer_id')
    
    job = db.session.get(Job, job_id)
    printer = db.session.get(Printer, printer_id)

    if not job or not printer:
        flash("Auftrag oder Drucker nicht gefunden.", "danger")
        return redirect(url_for('jobs_bp.dashboard'))

    if printer.status != PrinterStatus.IDLE:
        flash(f"Drucker '{printer.name}' ist nicht im Leerlauf.", "warning")
        return redirect(url_for('jobs_bp.dashboard'))
    
    try:
        job.printer_id = printer_id
        job.status = JobStatus.ASSIGNED
        db.session.commit()
        flash(f"Auftrag '{job.name}' wurde Drucker '{printer.name}' zugewiesen.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler bei der Zuweisung: {e}", "danger")

    return redirect(url_for('jobs_bp.dashboard'))

def handle_csv_import(reader):
    required_headers = ['name', 'target_quantity_parts', 'material_short_text', 'gcode_filename']
    
    if not all(h in reader.fieldnames for h in required_headers):
        missing = [h for h in required_headers if h not in reader.fieldnames]
        raise ValueError(f"Fehlende Spalten in der CSV-Datei: {', '.join(missing)}")

    material_cache = {f"{mat.manufacturer.lower()} {mat.name.lower()}": mat.id for mat in FilamentType.query.all()}
    gcode_cache = {gcode.filename: gcode.id for gcode in GCodeFile.query.all()}
    
    for i, row in enumerate(reader):
        if not any(row.values()): continue
        try:
            material_text = row.get('material_short_text', '').strip().lower()
            material_id = material_cache.get(material_text)
            gcode_filename = row.get('gcode_filename', '').strip()
            gcode_id = gcode_cache.get(gcode_filename)
            end_date = None
            if row.get('estimated_end_date'):
                end_date = datetime.strptime(row['estimated_end_date'], '%d.%m.%Y').date()

            new_job = Job( name=row['name'], target_quantity_parts=int(row['target_quantity_parts']), material_short_text=row.get('material_short_text'), estimated_end_date=end_date, priority=int(row.get('priority', 1)), status=JobStatus.PENDING, is_archived=False, required_filament_type_id=material_id, gcode_file_id=gcode_id, material_number=row.get('material_number') )
            db.session.add(new_job)
        except (ValueError, TypeError) as e:
            db.session.rollback()
            raise ValueError(f"Fehler in CSV-Zeile {i+2}: {row}. Falscher Datentyp? Details: {e}")
    db.session.commit()

@jobs_bp.route('/import', methods=['POST'])
@login_required
def import_csv():
    if 'file' not in request.files:
        flash('Keine Datei für den Upload ausgewählt.', 'danger')
        return redirect(url_for('jobs_bp.list_jobs'))
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.csv'):
        flash('Bitte wählen Sie eine gültige .csv-Datei aus.', 'danger')
        return redirect(url_for('jobs_bp.list_jobs'))
        
    try:
        stream = codecs.iterdecode(file.stream, 'utf-8-sig')
        reader = csv.DictReader(stream, delimiter=';')
        handle_csv_import(reader)
        flash('Aufträge erfolgreich aus CSV importiert.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Importieren der CSV-Datei: {e}', 'danger')
        
    return redirect(url_for('jobs_bp.list_jobs'))

def get_job_field_map():
    return {
        'name': ('name', str), 'status': ('status', JobStatus), 'priority': ('priority', int),
        'target_quantity_parts': ('target_quantity_parts', int),
        'estimated_end_date': ('estimated_end_date', lambda d: datetime.strptime(d, '%Y-%m-%d').date() if d else None),
        'gcode_file_id': ('gcode_file_id', int), 'printer_id': ('printer_id', int),
        'required_filament_type_id': ('required_filament_type_id', int),
        'material_number': ('material_number', str), 'material_short_text': ('material_short_text', str),
        'source_stl_filename': ('source_stl_filename', str),
    }

@jobs_bp.route('/archive/export')
@login_required
def export_archive():
    archived_jobs = Job.query.filter(Job.is_archived == True).order_by(Job.end_time.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([ 'ID', 'Name', 'Status', 'Qualitaet', 'Drucker', 'GCode-Datei', 'Filament-Typ', 'Erstellt am', 'Gestartet am', 'Beendet am', 'Druckdauer (Min)', 'Materialkosten', 'Maschinenkosten', 'Personalkosten', 'Gesamtkosten' ])
    for job in archived_jobs:
        writer.writerow([ job.id, job.name, job.status.value if job.status else '', job.quality_assessment.value if job.quality_assessment else '', job.assigned_printer.name if job.assigned_printer else 'N/A', job.gcode_file.filename if job.gcode_file else 'N/A', job.required_filament_type.name if job.required_filament_type else 'N/A', job.created_at.strftime('%Y-%m-%d %H:%M:%S') if job.created_at else '', job.start_time.strftime('%Y-%m-%d %H:%M:%S') if job.start_time else '', job.end_time.strftime('%Y-%m-%d %H:%M:%S') if job.end_time else '', round(job.actual_print_duration_s / 60, 2) if job.actual_print_duration_s else 0, job.material_cost, job.machine_cost, job.personnel_cost, job.total_cost ])
    output.seek(0)
    return Response( output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=archivierte_auftraege.csv"} )