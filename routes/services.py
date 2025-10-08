# routes/services.py
from flask import flash, has_request_context, current_app
from models import db, Job, Printer, JobStatus, JobQuality, PrinterStatus, FilamentSpool, PrinterStatusLog
import datetime
from extensions import socketio 

def _log_printer_status(printer, new_status):
    """Erstellt einen neuen Log-Eintrag für eine Drucker-Statusänderung."""
    if printer and new_status:
        log_entry = PrinterStatusLog(printer_id=printer.id, status=new_status)
        db.session.add(log_entry)
        print(f"DEBUG: Logge neuen Status '{new_status.name}' für Drucker '{printer.name}'")

def assign_job_to_printer(job_id, printer_id):
    #... (unverändert)
    job = db.session.get(Job, int(job_id))
    printer = db.session.get(Printer, int(printer_id))

    if not job or not printer:
        return False, "Job oder Drucker nicht gefunden."

    if job.required_filament_type_id:
        required_material_type = job.required_filament_type.material_type.upper()
        compatible_types = [pt.strip().upper() for pt in printer.compatible_material_types.split(',')]
        if required_material_type not in compatible_types:
            message = f'Inkompatibel: Drucker "{printer.name}" unterstützt nicht das Material "{required_material_type}".'
            return False, message

    job.printer_id = printer.id
    
    is_printer_busy = printer.jobs.filter(Job.status.in_([JobStatus.PRINTING, JobStatus.QUEUED])).count() > 0
    
    if printer.status == PrinterStatus.PRINTING or is_printer_busy:
        job.status = JobStatus.QUEUED
    else:
        job.status = JobStatus.ASSIGNED

    try:
        db.session.commit()
        return True, f'Job "{job.name}" wurde Drucker "{printer.name}" zugewiesen.'
    except Exception as e:
        db.session.rollback()
        return False, f"Datenbankfehler bei der Zuweisung: {e}"

def _update_printer_stats(job):
    """Diese Funktion ist leer. Statistiken werden jetzt automatisch berechnet."""
    pass

def _calculate_and_set_job_costs(job):
    #... (unverändert)
    if not job or not job.end_time or not job.start_time:
        return
    job.material_cost = 0.0
    if job.gcode_file and job.gcode_file.material_needed_g and job.required_filament_type and job.required_filament_type.cost_per_spool and job.required_filament_type.spool_weight_g and job.required_filament_type.spool_weight_g > 0:
        material_cost_per_g = job.required_filament_type.cost_per_spool / job.required_filament_type.spool_weight_g
        job.material_cost = job.gcode_file.material_needed_g * material_cost_per_g
    job.machine_cost = 0.0
    if job.assigned_printer:
        duration_hours = (job.end_time - job.start_time).total_seconds() / 3600
        cost_per_hour = job.assigned_printer.calculated_cost_per_hour or job.assigned_printer.cost_per_hour or 0
        energy_cost = 0.0
        if job.assigned_printer.power_consumption_w and job.assigned_printer.energy_price_kwh:
            power_kw = job.assigned_printer.power_consumption_w / 1000
            energy_cost = power_kw * duration_hours * job.assigned_printer.energy_price_kwh
        job.machine_cost = (duration_hours * cost_per_hour) + energy_cost
    job.personnel_cost = 0.0
    
    if job.employee_hourly_rate:
        total_manual_time_hours = ((job.preparation_time_min or 0) + (job.post_processing_time_min or 0)) / 60
        job.personnel_cost = total_manual_time_hours * job.employee_hourly_rate
        
    job.total_cost = (job.material_cost or 0) + (job.machine_cost or 0) + (job.personnel_cost or 0)

def _deduct_filament_from_spool(job):
    #... (unverändert)
    if not job.assigned_printer or not job.gcode_file or not job.gcode_file.material_needed_g:
        return

    active_spool = job.assigned_printer.assigned_spools.filter_by(is_in_use=True).first()
    
    if active_spool:
        filament_to_deduct = job.gcode_file.material_needed_g
        
        if active_spool.current_weight_g >= filament_to_deduct:
            active_spool.current_weight_g -= filament_to_deduct
        else:
            print(f"Warnung: Spule {active_spool.short_id} hat nicht genug Filament für Job {job.id}. Setze Gewicht auf 0.")
            active_spool.current_weight_g = 0
        
        print(f"Info: {filament_to_deduct}g von Spule {active_spool.short_id} abgezogen. Neues Gewicht: {active_spool.current_weight_g}g.")

def update_job_status(job_id, new_status_str, auto_retry_failed=False):
    job = db.session.get(Job, job_id)
    if not job: return False, "Auftrag nicht gefunden."

    try:
        new_status = JobStatus[new_status_str.upper()]
    except KeyError:
        return False, f"Ungültiger Status: {new_status_str}"

    job.status = new_status
    
    if new_status == JobStatus.COMPLETED:
        job.end_time = datetime.datetime.utcnow()
        job.completed_at = job.end_time
        if job.start_time:
            job.actual_print_duration_s = (job.end_time - job.start_time).total_seconds()
        
        _calculate_and_set_job_costs(job)
        _update_printer_stats(job)
        _deduct_filament_from_spool(job)
        
        if job.assigned_printer:
            job.assigned_printer.status = PrinterStatus.IDLE
            _log_printer_status(job.assigned_printer, PrinterStatus.IDLE) # <-- HINZUGEFÜGT

    elif new_status == JobStatus.PRINTING:
        if not job.start_time:
            job.start_time = datetime.datetime.utcnow()
        if job.assigned_printer:
            job.assigned_printer.status = PrinterStatus.PRINTING
            _log_printer_status(job.assigned_printer, PrinterStatus.PRINTING) # <-- HINZUGEFÜGT

    elif new_status in [JobStatus.FAILED, JobStatus.CANCELLED]:
        job.end_time = datetime.datetime.utcnow()
        if job.assigned_printer:
            job.assigned_printer.status = PrinterStatus.IDLE
            _log_printer_status(job.assigned_printer, PrinterStatus.IDLE) # <-- HINZUGEFÜGT
        if new_status == JobStatus.FAILED and auto_retry_failed:
            job.quality_assessment = JobQuality.FAILED
            new_job = Job(name=f"[RETRY] {job.name}", status=JobStatus.PENDING, priority=job.priority, gcode_file_id=job.gcode_file_id)
            db.session.add(new_job)
            job.is_archived = True
            if has_request_context():
                flash(f"Fehlgeschlagener Auftrag '{job.name}' wurde archiviert und ein neuer Ersatzauftrag '{new_job.name}' wurde erstellt.", "info")

    db.session.commit()
    
    if has_request_context():
        socketio.emit('reload_dashboard')

    return True, f"Status von Job '{job.name}' auf '{new_status.value}' gesetzt."