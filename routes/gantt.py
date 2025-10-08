# routes/gantt.py
from flask import Blueprint, jsonify
from flask_login import login_required
from models import Printer, Job, JobStatus
import datetime

gantt_bp = Blueprint('gantt_bp', __name__)

@gantt_bp.route('/printer/<int:printer_id>')
@login_required
def printer_gantt(printer_id):
    """
    Bereitet die Daten für das Gantt-Diagramm eines Druckers vor.
    Beinhaltet den aktuellen Job, sowie alle zugewiesenen und in der Warteschlange befindlichen Jobs.
    """
    printer = Printer.query.get_or_404(printer_id)
    jobs = printer.jobs.filter(
        Job.status.in_([JobStatus.PRINTING, JobStatus.ASSIGNED, JobStatus.QUEUED])
    ).order_by(Job.priority.desc(), Job.created_at.asc()).all()

    series_data = []
    
    # Startzeitpunkt für die Planung ist jetzt
    last_end_time = datetime.datetime.utcnow()

    for job in jobs:
        # Wenn der Job bereits läuft
        if job.status == JobStatus.PRINTING and job.start_time:
            start_time = job.start_time
            if job.gcode_file and job.gcode_file.estimated_print_time_min:
                duration_seconds = job.gcode_file.estimated_print_time_min * 60
                end_time = start_time + datetime.timedelta(seconds=duration_seconds)
            else: # Fallback, wenn keine Zeit vorhanden ist
                end_time = start_time + datetime.timedelta(hours=1)
        # Für geplante Jobs
        else:
            start_time = last_end_time
            if job.gcode_file and job.gcode_file.estimated_print_time_min:
                duration_seconds = job.gcode_file.estimated_print_time_min * 60
                end_time = start_time + datetime.timedelta(seconds=duration_seconds)
            else: # Fallback
                end_time = start_time + datetime.timedelta(hours=1)
        
        series_data.append({
            'x': job.name,
            'y': [
                start_time.timestamp() * 1000,
                end_time.timestamp() * 1000
            ],
            'fillColor': '#dc3545' if job.status == JobStatus.PRINTING else ('#ffc107' if job.status == JobStatus.ASSIGNED else '#0dcaf0')
        })

        # Die Endzeit dieses Jobs ist die Startzeit des nächsten
        last_end_time = end_time

    return jsonify([{'name': 'Belegung', 'data': series_data}])