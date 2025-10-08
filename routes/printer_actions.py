# /routes/printer_actions.py
from flask import Blueprint, redirect, url_for, flash
from flask_login import login_required
from extensions import db, socketio
from models import Job, JobStatus, PrinterStatus
from datetime import datetime
# KORRIGIERTER IMPORT: Wir nutzen die zentrale Status-Update-Funktion
from .services import update_job_status

printer_actions_bp = Blueprint('printer_actions_bp', __name__, url_prefix='/printer_actions')

@printer_actions_bp.route('/job/start/<int:job_id>', methods=['POST'])
@login_required
def start_job(job_id):
    job = db.session.get(Job, job_id)
    if job and job.assigned_printer:
        # Status-Änderung über den Service
        success, message = update_job_status(job_id, 'PRINTING')
        if success:
            flash(f'Auftrag "{job.name}" wurde gestartet.', 'success')
            socketio.emit('reload_dashboard')
        else:
            flash(message, 'danger')
    else:
        flash('Auftrag kann nicht gestartet werden (nicht gefunden oder kein Drucker zugewiesen).', 'danger')
    # HIER IST DIE KORREKTUR
    return redirect(url_for('jobs_bp.dashboard'))

@printer_actions_bp.route('/job/pause/<int:job_id>', methods=['POST'])
@login_required
def pause_job(job_id):
    job = db.session.get(Job, job_id)
    if job and job.assigned_printer and job.status == JobStatus.PRINTING:
        # Hier könnte man einen PAUSED-Status einführen, fürs Erste nutzen wir QUEUED
        success, message = update_job_status(job_id, 'QUEUED')
        if success:
            job.assigned_printer.status = PrinterStatus.IDLE # Oder PAUSED
            db.session.commit()
            flash(f'Auftrag "{job.name}" wurde pausiert.', 'warning')
            socketio.emit('reload_dashboard')
        else:
            flash(message, 'danger')
    else:
        flash('Laufender Auftrag kann nicht pausiert werden.', 'danger')
    # HIER IST DIE KORREKTUR
    return redirect(url_for('jobs_bp.dashboard'))

@printer_actions_bp.route('/job/stop/<int:job_id>', methods=['POST'])
@login_required
def stop_job(job_id):
    job = db.session.get(Job, job_id)
    if job and job.assigned_printer:
        # Die gesamte Logik (Status, Endzeit, Kosten, Drucker-Stats) wird jetzt vom Service gehandhabt
        success, message = update_job_status(job_id, 'COMPLETED')
        if success:
            flash(f'Auftrag "{job.name}" wurde beendet und als abgeschlossen markiert.', 'success')
            socketio.emit('reload_dashboard')
        else:
            flash(message, 'danger')
    else:
        flash('Auftrag kann nicht gestoppt werden.', 'danger')
    # HIER IST DIE KORREKTUR
    return redirect(url_for('jobs_bp.dashboard'))