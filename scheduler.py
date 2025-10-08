import os
import atexit
import datetime
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from models import Printer, PrinterStatusLog, PrinterStatus, Job, JobStatus, PrintSnapshot, SystemSetting
from extensions import db
from printer_communication import get_printer_status # Wichtiger Import
from job_optimizer import find_best_printer_for_job
from routes.services import assign_job_to_printer, update_job_status

def take_snapshots(app):
    """
    Nimmt von allen Druckern, die gerade drucken und eine Webcam-URL haben,
    ein Bild auf und speichert es.
    """
    with app.app_context():
        printing_printers = Printer.query.filter(
            Printer.status == PrinterStatus.PRINTING, 
            Printer.webcam_url.isnot(None)
        ).all()

        if not printing_printers:
            return

        for printer in printing_printers:
            current_job = printer.get_current_job()
            if not current_job or not printer.webcam_url:
                continue

            try:
                url = f"{printer.webcam_url}?t={datetime.datetime.now().timestamp()}"
                response = requests.get(url, stream=True, timeout=5)
                response.raise_for_status()
                
                base_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'snapshots')
                os.makedirs(base_dir, exist_ok=True)
                
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"job_{current_job.id}_printer_{printer.id}_{timestamp_str}.jpg"
                filepath = os.path.join(base_dir, filename)
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                
                new_snapshot = PrintSnapshot(job_id=current_job.id, image_filename=filename)
                db.session.add(new_snapshot)
                db.session.commit()

            except requests.exceptions.RequestException as e:
                print(f"Fehler beim Abrufen des Webcam-Bildes von {printer.name}: {e}")
            except Exception as e:
                db.session.rollback()
                print(f"Fehler beim Speichern des Snapshots für Job {current_job.id}: {e}")

def check_and_broadcast_status(app, socketio):
    """
    Überprüft den Status aller Drucker, aktualisiert die DB, weist bei Bedarf neue Jobs zu
    und sendet den Live-Status an alle Clients.
    """
    with app.app_context():
        change_detected = False
        
        # --- 1. Automatische Job-Zuweisung (bestehende Logik) ---
        scheduler_setting = SystemSetting.query.filter_by(key='scheduler_enabled').first()
        is_scheduler_enabled = scheduler_setting.value.lower() == 'true' if scheduler_setting else True

        if is_scheduler_enabled:
            pending_jobs = Job.query.filter(Job.status == JobStatus.PENDING).order_by(Job.priority.desc(), Job.created_at.asc()).all()
            if pending_jobs:
                for job in pending_jobs:
                    best_printer = find_best_printer_for_job(job)
                    if best_printer:
                        success, message = assign_job_to_printer(job.id, best_printer.id)
                        if success: change_detected = True
        
        # Wenn durch die Zuweisung eine Änderung stattfand, sende sofort ein Update
        if change_detected:
            socketio.emit('reload_dashboard')
            print("Scheduler: Änderungen bei Job-Zuweisung erkannt, sende Reload-Signal.")

        # --- 2. NEU: Kontinuierliche Live-Status-Abfrage und Broadcast ---
        try:
            printers = Printer.query.all()
            full_status_data = {}
            for printer in printers:
                # Diese Funktion holt den ECHTZEIT-Status von Klipper/OctoPrint, wenn konfiguriert
                status_dict = get_printer_status(printer)
                full_status_data[printer.id] = status_dict
            
            # Sende die gesammelten Live-Daten an alle verbundenen Dashboards
            socketio.emit('status_update', full_status_data)
            
        except Exception as e:
            print(f"Scheduler-Fehler bei Live-Status-Abfrage: {e}")

        
def check_and_complete_jobs_automatically(app):
    """
    Überprüft alle laufenden Druckaufträge und beendet sie automatisch,
    wenn ihre geschätzte Druckzeit abgelaufen ist.
    """
    with app.app_context():
        printing_jobs = Job.query.filter_by(status=JobStatus.PRINTING).filter(Job.start_time.isnot(None)).all()
        
        if not printing_jobs:
            return

        for job in printing_jobs:
            if not job.gcode_file or not job.gcode_file.estimated_print_time_min:
                continue

            estimated_end_time = job.start_time + datetime.timedelta(minutes=job.gcode_file.estimated_print_time_min)
            
            if datetime.datetime.utcnow() >= estimated_end_time:
                print(f"Auto-Complete: Auftrag '{job.name}' (ID: {job.id}) hat seine Zeit erreicht. Beende automatisch.")
                update_job_status(job.id, 'COMPLETED')


def init_scheduler(app, socketio):
    """Initialisiert und startet den Hintergrund-Scheduler."""
    scheduler = BackgroundScheduler(daemon=True)
    
    # Dieser Job läuft jetzt alle 5 Sekunden und sorgt für die Live-Updates
    scheduler.add_job(
        func=lambda: check_and_broadcast_status(app, socketio), 
        trigger="interval", 
        seconds=5,
        id="job_assigner_and_status_broadcaster"
    )
    
    scheduler.add_job(
        func=lambda: take_snapshots(app),
        trigger="interval",
        minutes=1,
        id="snapshot_taker"
    )

    scheduler.add_job(
        func=lambda: check_and_complete_jobs_automatically(app),
        trigger="interval",
        minutes=1,
        id="job_completer"
    )

    scheduler.start()
    print("Scheduler mit Live-Status-Broadcast erfolgreich gestartet.")
    atexit.register(lambda: scheduler.shutdown())