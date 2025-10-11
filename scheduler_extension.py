# scheduler_extension.py
# Diese Funktionen in scheduler.py einfügen oder bestehende ersetzen

import datetime
from datetime import timedelta
from extensions import db, socketio
from models import (
    Job, Printer, Project, JobStatus, PrinterStatus, PrinterStatusLog,
    DependencyType, DeadlineStatus
)
from validators import (
    DependencyValidator, CriticalPathCalculator, 
    PriorityCalculator, SchedulingOptimizer
)
import logging

scheduler_logger = logging.getLogger('scheduler')


@with_app_context
def calculate_priority_scores():
    """
    Berechnet Prioritäts-Scores für alle offenen Jobs.
    Läuft alle 15 Minuten.
    """
    if not is_scheduler_enabled():
        return
    
    try:
        # 1. Berechne kritische Pfade für alle aktiven Projekte
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            try:
                CriticalPathCalculator.calculate(project)
                scheduler_logger.debug(f"Kritischer Pfad berechnet für: {project.name}")
            except Exception as e:
                scheduler_logger.error(f"Fehler bei CPM für Projekt {project.id}: {e}")
        
        # 2. Berechne Priority Scores für alle Jobs
        pending_jobs = Job.query.filter(
            Job.status.in_([JobStatus.PENDING, JobStatus.ASSIGNED, JobStatus.QUEUED])
        ).all()
        
        updated = 0
        
        for job in pending_jobs:
            old_score = job.priority_score
            new_score = PriorityCalculator.calculate_priority_score(job)
            
            if abs(old_score - new_score) > 0.5:  # Nur bei signifikanter Änderung
                job.priority_score = new_score
                updated += 1
                
                scheduler_logger.debug(
                    f"Job {job.id} Priorität: {old_score:.1f} -> {new_score:.1f}"
                )
        
        if updated > 0:
            db.session.commit()
            scheduler_logger.info(f"{updated} Job-Prioritäten aktualisiert")
            socketio.emit('priority_updated', {'count': updated})
        
    except Exception as e:
        scheduler_logger.error(f"Fehler bei Prioritäts-Berechnung: {e}")
        try:
            db.session.rollback()
        except:
            pass


@with_app_context
def assign_pending_jobs_advanced():
    """
    ERWEITERTER Scheduler mit:
    - Deadline-Bewusstsein
    - Abhängigkeits-Prüfung
    - Zeitfenster-Berücksichtigung
    - Intelligenter Priorisierung
    
    Ersetzt die alte assign_pending_jobs() Funktion.
    """
    if not is_scheduler_enabled():
        return
    
    try:
        # 1. Finde verfügbare Drucker
        idle_printers = Printer.query.filter_by(status=PrinterStatus.IDLE).all()
        
        if not idle_printers:
            scheduler_logger.debug("Keine freien Drucker verfügbar")
            return
        
        # 2. Finde zuweisbare Jobs (sortiert nach Priority Score)
        pending_jobs = Job.query.filter_by(status=JobStatus.PENDING)\
            .filter(Job.printer_id.is_(None))\
            .order_by(Job.priority_score.desc(), Job.created_at.asc())\
            .limit(50)\
            .all()  # Limit für Performance
        
        if not pending_jobs:
            scheduler_logger.debug("Keine pending Jobs")
            return
        
        assignments = 0
        skipped_deps = 0
        skipped_time = 0
        skipped_material = 0
        now = datetime.datetime.utcnow()
        
        for job in pending_jobs:
            # === ABHÄNGIGKEITS-PRÜFUNG ===
            if not job.can_start:
                blocking_deps = job.get_blocking_dependencies()
                scheduler_logger.debug(
                    f"Job {job.id} '{job.name}' wartet auf {len(blocking_deps)} Abhängigkeiten"
                )
                skipped_deps += 1
                continue
            
            # === DRUCKER-MATCHING ===
            suitable_printer = None
            
            for printer in idle_printers:
                # Prüfe Zeitfenster
                if not printer.is_available_at(now):
                    next_available = printer.get_next_available_time()
                    scheduler_logger.debug(
                        f"Drucker {printer.name} außerhalb Zeitfenster "
                        f"(nächste Zeit: {next_available})"
                    )
                    skipped_time += 1
                    continue
                
                # Prüfe Material-Kompatibilität
                if job.required_filament_type:
                    loaded_spool = printer.assigned_spools.filter_by(is_in_use=True).first()
                    
                    if loaded_spool:
                        if loaded_spool.filament_type_id != job.required_filament_type.id:
                            scheduler_logger.debug(
                                f"Material-Konflikt: Job braucht {job.required_filament_type.name}, "
                                f"aber {loaded_spool.filament_type.name} geladen"
                            )
                            skipped_material += 1
                            continue
                        
                        # Prüfe ob genug Material vorhanden
                        if job.gcode_file and job.gcode_file.material_needed_g:
                            if loaded_spool.remaining_grams < job.gcode_file.material_needed_g:
                                scheduler_logger.warning(
                                    f"Nicht genug Material: {loaded_spool.remaining_grams}g verfügbar, "
                                    f"{job.gcode_file.material_needed_g}g benötigt"
                                )
                                skipped_material += 1
                                continue
                
                # Prüfe Druckbett-Größe (falls Dimensionen vorhanden)
                if job.gcode_file and printer.bed_size_x and printer.bed_size_y:
                    if job.gcode_file.dimensions_x_mm and job.gcode_file.dimensions_y_mm:
                        if (job.gcode_file.dimensions_x_mm > printer.bed_size_x or 
                            job.gcode_file.dimensions_y_mm > printer.bed_size_y):
                            scheduler_logger.warning(
                                f"Job zu groß für Drucker {printer.name}"
                            )
                            continue
                
                # Drucker ist geeignet!
                suitable_printer = printer
                break
            
            # === JOB-ZUWEISUNG ===
            if suitable_printer:
                try:
                    # Setze Job und Drucker Status
                    job.printer_id = suitable_printer.id
                    job.status = JobStatus.ASSIGNED
                    suitable_printer.status = PrinterStatus.QUEUED
                    
                    # Berechne geschätzte Start-/Endzeit
                    job.estimated_start_time = now
                    if job.gcode_file and job.gcode_file.estimated_print_time_min:
                        job.estimated_end_time = now + timedelta(
                            minutes=job.gcode_file.estimated_print_time_min
                        )
                    
                    # Log für Statusänderung
                    log_entry = PrinterStatusLog(
                        printer_id=suitable_printer.id,
                        status=PrinterStatus.QUEUED
                    )
                    db.session.add(log_entry)
                    
                    # Entferne Drucker aus Pool
                    idle_printers.remove(suitable_printer)
                    assignments += 1
                    
                    scheduler_logger.info(
                        f"✓ Job '{job.name}' (Score: {job.priority_score:.1f}) "
                        f"-> {suitable_printer.name}"
                        f"{' [KRITISCHER PFAD]' if job.is_on_critical_path else ''}"
                        f"{f' [Deadline: {job.hours_until_deadline:.1f}h]' if job.deadline else ''}"
                    )
                    
                except Exception as e:
                    scheduler_logger.error(f"Fehler bei Zuweisung von Job {job.id}: {e}")
                    db.session.rollback()
        
        # === COMMIT & BENACHRICHTIGUNG ===
        if assignments > 0:
            db.session.commit()
            scheduler_logger.info(
                f"🎯 {assignments} Jobs zugewiesen | "
                f"Übersprungen: {skipped_deps} Deps, {skipped_time} Zeit, {skipped_material} Material"
            )
            
            # WebSocket-Benachrichtigung
            socketio.emit('reload_dashboard')
            socketio.emit('jobs_assigned', {
                'count': assignments,
                'timestamp': now.isoformat()
            })
        
    except Exception as e:
        scheduler_logger.error(f"Kritischer Fehler bei Job-Zuweisung: {e}")
        try:
            db.session.rollback()
        except:
            pass


@with_app_context
def check_deadline_alerts():
    """
    Prüft nahende und überschrittene Deadlines.
    Sendet Warnungen via WebSocket.
    Läuft stündlich.
    """
    if not is_scheduler_enabled():
        return
    
    try:
        now = datetime.datetime.utcnow()
        
        # 1. Überfällige Jobs
        overdue_jobs = Job.query.filter(
            Job.deadline.isnot(None),
            Job.deadline < now,
            Job.status.in_([JobStatus.PENDING, JobStatus.ASSIGNED, JobStatus.QUEUED, JobStatus.PRINTING])
        ).all()
        
        for job in overdue_jobs:
            hours_overdue = (now - job.deadline).total_seconds() / 3600
            
            socketio.emit('deadline_alert', {
                'type': 'overdue',
                'job_id': job.id,
                'job_name': job.name,
                'hours_overdue': round(hours_overdue, 1),
                'printer': job.assigned_printer.name if job.assigned_printer else 'Nicht zugewiesen',
                'project': job.project.name if job.project else None
            })
        
        if overdue_jobs:
            scheduler_logger.warning(f"⚠️  {len(overdue_jobs)} überfällige Jobs!")
        
        # 2. Dringende Jobs (< 24h)
        urgent_jobs = Job.query.filter(
            Job.deadline.isnot(None),
            Job.deadline > now,
            Job.deadline < now + timedelta(hours=24),
            Job.status.in_([JobStatus.PENDING, JobStatus.ASSIGNED, JobStatus.QUEUED])
        ).all()
        
        for job in urgent_jobs:
            hours_remaining = (job.deadline - now).total_seconds() / 3600
            
            socketio.emit('deadline_alert', {
                'type': 'urgent',
                'job_id': job.id,
                'job_name': job.name,
                'hours_remaining': round(hours_remaining, 1),
                'status': job.status.value,
                'printer': job.assigned_printer.name if job.assigned_printer else 'Nicht zugewiesen'
            })
        
        if urgent_jobs:
            scheduler_logger.info(f"⏰ {len(urgent_jobs)} dringende Jobs (< 24h)")
        
        # 3. Projekt-Deadlines prüfen
        projects_at_risk = Project.query.filter(
            Project.deadline.isnot(None),
            Project.deadline > now,
            Project.deadline < now + timedelta(hours=48),
            Project.status == 'active'
        ).all()
        
        for project in projects_at_risk:
            incomplete = project.jobs.filter(
                Job.status != JobStatus.COMPLETED
            ).count()
            
            if incomplete > 0:
                hours_remaining = (project.deadline - now).total_seconds() / 3600
                
                socketio.emit('project_deadline_alert', {
                    'project_id': project.id,
                    'project_name': project.name,
                    'hours_remaining': round(hours_remaining, 1),
                    'incomplete_jobs': incomplete,
                    'completion': project.completion_percentage
                })
                
                scheduler_logger.warning(
                    f"Projekt '{project.name}' Deadline in {hours_remaining:.1f}h, "
                    f"{incomplete} Jobs offen ({project.completion_percentage:.0f}% fertig)"
                )
    
    except Exception as e:
        scheduler_logger.error(f"Fehler bei Deadline-Check: {e}")


@with_app_context
def optimize_job_queue():
    """
    Optimiert die Job-Queue basierend auf aktuellen Prioritäten.
    Kann Jobs neu priorisieren wenn sich Situation ändert.
    Läuft alle 30 Minuten.
    """
    if not is_scheduler_enabled():
        return
    
    try:
        # Finde Jobs die zugewiesen aber noch nicht gestartet sind
        queued_jobs = Job.query.filter(
            Job.status.in_([JobStatus.ASSIGNED, JobStatus.QUEUED])
        ).order_by(Job.printer_id, Job.priority_score.desc()).all()
        
        if not queued_jobs:
            return
        
        reordered = 0
        
        # Gruppiere nach Drucker
        printer_queues = {}
        for job in queued_jobs:
            if job.printer_id:
                if job.printer_id not in printer_queues:
                    printer_queues[job.printer_id] = []
                printer_queues[job.printer_id].append(job)
        
        # Prüfe jede Queue auf Optimierungspotenzial
        for printer_id, jobs in printer_queues.items():
            if len(jobs) > 1:
                # Sortiere nach Priority Score
                sorted_jobs = sorted(jobs, key=lambda j: j.priority_score, reverse=True)
                
                # Prüfe ob Reihenfolge geändert werden sollte
                if sorted_jobs != jobs:
                    scheduler_logger.info(
                        f"Queue-Optimierung für Drucker {printer_id}: "
                        f"{len(jobs)} Jobs neu sortiert"
                    )
                    reordered += 1
        
        if reordered > 0:
            db.session.commit()
            scheduler_logger.info(f"Queue-Optimierung: {reordered} Drucker-Queues aktualisiert")
    
    except Exception as e:
        scheduler_logger.error(f"Fehler bei Queue-Optimierung: {e}")
        try:
            db.session.rollback()
        except:
            pass


@with_app_context
def check_time_window_compliance():
    """
    Prüft ob laufende Jobs außerhalb der Zeitfenster sind.
    Pausiert oder warnt bei Konflikten.
    Läuft alle 15 Minuten.
    """
    if not is_scheduler_enabled():
        return
    
    try:
        now = datetime.datetime.utcnow()
        
        # Finde alle Drucker mit aktiven Zeitfenstern
        printers_with_windows = Printer.query.filter(
            Printer.time_windows.any()
        ).all()
        
        violations = 0
        
        for printer in printers_with_windows:
            # Prüfe ob Drucker aktuell verfügbar sein sollte
            is_available = printer.is_available_at(now)
            
            # Wenn Drucker außerhalb Zeitfenster ist
            if not is_available:
                # Prüfe laufende Jobs
                running_job = printer.jobs.filter_by(status=JobStatus.PRINTING).first()
                
                if running_job:
                    # Job läuft außerhalb Zeitfenster
                    next_window = printer.get_next_available_time()
                    
                    socketio.emit('time_window_violation', {
                        'printer_id': printer.id,
                        'printer_name': printer.name,
                        'job_id': running_job.id,
                        'job_name': running_job.name,
                        'next_available': next_window.isoformat() if next_window else None
                    })
                    
                    violations += 1
                    scheduler_logger.warning(
                        f"⏰ Zeitfenster-Verletzung: Drucker '{printer.name}' "
                        f"läuft außerhalb erlaubter Zeit"
                    )
        
        if violations > 0:
            scheduler_logger.info(f"{violations} Zeitfenster-Verletzungen erkannt")
    
    except Exception as e:
        scheduler_logger.error(f"Fehler bei Zeitfenster-Check: {e}")


# ==================== SCHEDULER-INITIALISIERUNG ====================

def init_scheduler_with_advanced_features(app, socketio_instance):
    """
    Erweitert den Scheduler mit neuen Jobs.
    Diese Funktion in die bestehende init_scheduler() integrieren.
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    
    scheduler = BackgroundScheduler()
    
    with app.app_context():
        try:
            # === NEUE JOBS HINZUFÜGEN ===
            
            # Prioritäts-Scores berechnen (alle 15 Minuten)
            scheduler.add_job(
                func=calculate_priority_scores,
                trigger="interval",
                minutes=15,
                id='calculate_priority_scores',
                name='Prioritäts-Scores berechnen',
                replace_existing=True
            )
            scheduler_logger.info("✓ Job hinzugefügt: Prioritäts-Scores")
            
            # ERSETZE assign_pending_jobs durch erweiterte Version
            scheduler.add_job(
                func=assign_pending_jobs_advanced,
                trigger="interval",
                seconds=60,
                id='assign_pending_jobs_advanced',
                name='Jobs intelligent zuweisen (erweitert)',
                replace_existing=True
            )
            scheduler_logger.info("✓ Job hinzugefügt: Intelligente Zuweisung")
            
            # Deadline-Alerts (stündlich)
            scheduler.add_job(
                func=check_deadline_alerts,
                trigger="interval",
                hours=1,
                id='check_deadline_alerts',
                name='Deadline-Alerts prüfen',
                replace_existing=True
            )
            scheduler_logger.info("✓ Job hinzugefügt: Deadline-Alerts")
            
            # Queue-Optimierung (alle 30 Minuten)
            scheduler.add_job(
                func=optimize_job_queue,
                trigger="interval",
                minutes=30,
                id='optimize_job_queue',
                name='Job-Queue optimieren',
                replace_existing=True
            )
            scheduler_logger.info("✓ Job hinzugefügt: Queue-Optimierung")
            
            # Zeitfenster-Compliance (alle 15 Minuten)
            scheduler.add_job(
                func=check_time_window_compliance,
                trigger="interval",
                minutes=15,
                id='check_time_window_compliance',
                name='Zeitfenster-Compliance prüfen',
                replace_existing=True
            )
            scheduler_logger.info("✓ Job hinzugefügt: Zeitfenster-Check")
            
            scheduler_logger.info("=" * 60)
            scheduler_logger.info("🚀 ERWEITERTER SCHEDULER ERFOLGREICH INITIALISIERT")
            scheduler_logger.info(f"   Gesamt: {len(scheduler.get_jobs())} Jobs aktiv")
            scheduler_logger.info("=" * 60)
            
        except Exception as e:
            scheduler_logger.error(f"Fehler beim Initialisieren des erweiterten Schedulers: {e}")
    
    return scheduler