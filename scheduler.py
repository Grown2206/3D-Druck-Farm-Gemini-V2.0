import atexit
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import uuid
from flask import current_app
from extensions import db, socketio
from models import Printer, Job, JobStatus, PrinterStatus, PrinterStatusLog, FilamentSpool, FilamentType, SystemSetting
from printer_communication import get_printer_status
import logging

# Logger für Scheduler
scheduler_logger = logging.getLogger('scheduler')

# Globaler App Context für Scheduler Jobs
_app_context = None

def set_app_context(app):
    """Setzt den App Context für Scheduler Jobs"""
    global _app_context
    _app_context = app

def with_app_context(func):
    """Decorator für App Context in Scheduler Jobs"""
    def wrapper(*args, **kwargs):
        if _app_context:
            with _app_context.app_context():
                return func(*args, **kwargs)
        else:
            scheduler_logger.error(f"Kein App Context für {func.__name__} verfügbar")
            return None
    return wrapper

def is_scheduler_enabled():
    """Prüft ob der Scheduler aktiviert ist"""
    try:
        setting = SystemSetting.query.filter_by(key='scheduler_enabled').first()
        return setting.value.lower() == 'true' if setting else True
    except:
        return True

@with_app_context
def check_job_completion():
    """Prüft und beendet Jobs automatisch basierend auf geschätzter Druckzeit"""
    if not is_scheduler_enabled():
        return
        
    try:
        # Finde alle PRINTING Jobs
        printing_jobs = Job.query.filter_by(status=JobStatus.PRINTING).all()
        
        completed_jobs = 0
        
        for job in printing_jobs:
            # Prüfe ob Job abgeschlossen werden kann
            if should_complete_job(job):
                try:
                    complete_job_automatically(job)
                    completed_jobs += 1
                    scheduler_logger.info(f"Job '{job.name}' automatisch abgeschlossen")
                except Exception as job_error:
                    scheduler_logger.error(f"Fehler beim Abschließen von Job {job.id}: {job_error}")
        
        if completed_jobs > 0:
            db.session.commit()
            scheduler_logger.info(f"{completed_jobs} Jobs automatisch abgeschlossen")
            
            # Status-Broadcast auslösen
            socketio.emit('reload_dashboard')
        
    except Exception as e:
        scheduler_logger.error(f"Fehler bei automatischer Job-Completion: {e}")
        try:
            db.session.rollback()
        except:
            pass

def should_complete_job(job):
    """Prüft ob ein Job abgeschlossen werden sollte"""
    # Job muss gestartet sein
    if not job.start_time:
        return False
    
    # Job muss GCode-Datei mit geschätzter Zeit haben
    if not job.gcode_file or not job.gcode_file.estimated_print_time_min:
        return False
    
    # Berechne ob geschätzte Zeit abgelaufen ist
    estimated_duration = timedelta(minutes=job.gcode_file.estimated_print_time_min)
    estimated_end_time = job.start_time + estimated_duration
    
    # Job gilt als abgeschlossen wenn geschätzte Zeit + 5 Minuten Puffer abgelaufen
    buffer_time = timedelta(minutes=5)
    return datetime.utcnow() >= (estimated_end_time + buffer_time)

def complete_job_automatically(job):
    """Schließt einen Job automatisch ab"""
    from routes.services import _calculate_and_set_job_costs, _deduct_filament_from_spool, _log_printer_status
    
    # Job-Status setzen
    job.status = JobStatus.COMPLETED
    job.end_time = datetime.utcnow()
    job.completed_at = job.end_time
    
    # Tatsächliche Druckdauer berechnen
    if job.start_time:
        job.actual_print_duration_s = int((job.end_time - job.start_time).total_seconds())
    
    # Kosten berechnen
    _calculate_and_set_job_costs(job)
    
    # Filament abziehen
    _deduct_filament_from_spool(job)
    
    # Drucker-Status aktualisieren
    if job.assigned_printer:
        job.assigned_printer.status = PrinterStatus.IDLE
        _log_printer_status(job.assigned_printer, PrinterStatus.IDLE)
        
        scheduler_logger.info(f"Drucker {job.assigned_printer.name} auf IDLE gesetzt")

@with_app_context
def status_broadcast():
    """Sendet Live-Status-Updates über WebSocket"""
    if not is_scheduler_enabled():
        return
        
    try:
        # Drucker-Status sammeln
        printers = Printer.query.all()
        printer_data = []
        
        for printer in printers:
            status_info = {
                'id': printer.id,
                'name': printer.name,
                'status': printer.status.value,
                'current_job': None
            }
            
            # Aktueller Job
            current_job = printer.get_current_job()
            if current_job:
                status_info['current_job'] = {
                    'id': current_job.id,
                    'name': current_job.name,
                    'progress': current_job.get_manual_progress()
                }
            
            printer_data.append(status_info)
        
        # WebSocket-Broadcast
        socketio.emit('status_update', {
            'timestamp': datetime.utcnow().isoformat(),
            'printers': printer_data
        })
        
        scheduler_logger.debug(f"Status-Broadcast an {len(printer_data)} Drucker gesendet")
    
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Status-Broadcast: {e}")

@with_app_context
def update_printer_statuses():
    """Aktualisiert Drucker-Status über API-Abfragen"""
    if not is_scheduler_enabled():
        return
        
    try:
        printers = Printer.query.filter(
            Printer.api_type.in_(['KLIPPER', 'OCTOPRINT']),
            Printer.ip_address.isnot(None)
        ).all()
        
        updated_count = 0
        
        for printer in printers:
            try:
                # Status von Drucker abrufen
                api_status = get_printer_status(printer)
                
                if api_status and 'status' in api_status:
                    # Status-Mapping von API zu unseren Enums
                    status_mapping = {
                        'operational': PrinterStatus.IDLE,
                        'printing': PrinterStatus.PRINTING,
                        'paused': PrinterStatus.PRINTING,  # Pause als Printing behandeln
                        'error': PrinterStatus.ERROR,
                        'offline': PrinterStatus.OFFLINE,
                        'ready': PrinterStatus.IDLE,
                        'idle': PrinterStatus.IDLE
                    }
                    
                    api_status_lower = api_status['status'].lower()
                    new_status = status_mapping.get(api_status_lower)
                    
                    if new_status and printer.status != new_status:
                        old_status = printer.status
                        printer.status = new_status
                        
                        # Log-Eintrag erstellen
                        log_entry = PrinterStatusLog(
                            printer_id=printer.id,
                            status=new_status
                        )
                        db.session.add(log_entry)
                        updated_count += 1
                        
                        scheduler_logger.info(f"Status geändert: {printer.name} {old_status.value} -> {new_status.value}")
            
            except Exception as printer_error:
                scheduler_logger.warning(f"Fehler beim Aktualisieren von {printer.name}: {printer_error}")
        
        if updated_count > 0:
            db.session.commit()
            scheduler_logger.info(f"{updated_count} Drucker-Status aktualisiert")
    
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Aktualisieren der Drucker-Status: {e}")
        try:
            db.session.rollback()
        except:
            pass

@with_app_context
def assign_pending_jobs():
    """Weist wartende Jobs automatisch zu verfügbaren Druckern zu"""
    if not is_scheduler_enabled():
        return
        
    try:
        # Verfügbare Drucker finden
        idle_printers = Printer.query.filter_by(status=PrinterStatus.IDLE).all()
        
        if not idle_printers:
            scheduler_logger.debug("Keine verfügbaren Drucker für Job-Zuweisung")
            return
        
        # Wartende Jobs nach Priorität
        pending_jobs = Job.query.filter_by(
            status=JobStatus.PENDING
        ).order_by(
            Job.priority.desc(),
            Job.created_at.asc()
        ).all()
        
        if not pending_jobs:
            scheduler_logger.debug("Keine wartenden Jobs für Zuweisung")
            return
        
        assignments = 0
        
        for job in pending_jobs:
            if not idle_printers:
                break
                
            # Passenden Drucker finden
            suitable_printer = None
            
            for printer in idle_printers:
                # Material-Kompatibilität prüfen
                if job.required_filament_type_id:
                    # Prüfe ob passendes Material verfügbar
                    available_spools = FilamentSpool.query.filter_by(
                        filament_type_id=job.required_filament_type_id,
                        is_in_use=False
                    ).filter(FilamentSpool.current_weight_g > 0).all()
                    
                    if available_spools:
                        # Prüfe Drucker-Material-Kompatibilität
                        required_material = job.required_filament_type.material_type.upper()
                        compatible_materials = [m.strip().upper() for m in (printer.compatible_material_types or '').split(',')]
                        
                        if not compatible_materials or '' in compatible_materials or required_material in compatible_materials:
                            suitable_printer = printer
                            break
                else:
                    # Kein spezifisches Material erforderlich
                    suitable_printer = printer
                    break
            
            if suitable_printer:
                # Job zuweisen
                job.printer_id = suitable_printer.id
                job.status = JobStatus.ASSIGNED
                suitable_printer.status = PrinterStatus.QUEUED
                
                # Log für Statusänderung
                log_entry = PrinterStatusLog(
                    printer_id=suitable_printer.id,
                    status=PrinterStatus.QUEUED
                )
                db.session.add(log_entry)
                
                idle_printers.remove(suitable_printer)
                assignments += 1
                
                scheduler_logger.info(f"Job '{job.name}' zu {suitable_printer.name} zugewiesen")
        
        if assignments > 0:
            db.session.commit()
            scheduler_logger.info(f"{assignments} Jobs automatisch zugewiesen")
            
            # Status-Broadcast auslösen
            socketio.emit('reload_dashboard')
    
    except Exception as e:
        scheduler_logger.error(f"Fehler bei automatischer Job-Zuweisung: {e}")
        try:
            db.session.rollback()
        except:
            pass

@with_app_context
def check_drying_timers():
    """Prüft abgelaufene Trocknungszeiten"""
    try:
        overdue_spools = FilamentSpool.query.filter(
            FilamentSpool.is_drying == True,
            FilamentSpool.drying_end_time.isnot(None),
            FilamentSpool.drying_end_time <= datetime.utcnow()
        ).all()
        
        notification_count = 0
        
        for spool in overdue_spools:
            scheduler_logger.info(f"Trocknung abgelaufen: {spool.short_id}")
            
            # WebSocket-Benachrichtigung
            try:
                socketio.emit('drying_timer_alert', {
                    'spool_id': spool.id,
                    'spool_name': f"{spool.short_id} ({spool.filament_type.name})",
                    'message': f"Trocknung für Spule {spool.short_id} ist abgeschlossen!"
                })
                notification_count += 1
            except Exception as emit_error:
                scheduler_logger.warning(f"WebSocket-Benachrichtigung fehlgeschlagen: {emit_error}")
        
        if notification_count > 0:
            scheduler_logger.info(f"{notification_count} Trocknungs-Benachrichtigungen gesendet")
        
        return len(overdue_spools)
    
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Prüfen der Trocknungszeiten: {e}")
        return 0

@with_app_context
def check_low_filament_alerts():
    """Prüft niedrige Filamentbestände"""
    try:
        alerts = []
        
        filament_types = FilamentType.query.filter(
            FilamentType.reorder_level_g.isnot(None),
            FilamentType.reorder_level_g > 0
        ).all()
        
        for ftype in filament_types:
            total_weight = ftype.total_remaining_weight
            
            if total_weight <= ftype.reorder_level_g:
                alert = {
                    'material_id': ftype.id,
                    'material': f"{ftype.manufacturer} {ftype.name}",
                    'current_weight': total_weight,
                    'reorder_level': ftype.reorder_level_g,
                    'color': ftype.color_hex
                }
                alerts.append(alert)
                scheduler_logger.warning(f"Niedriger Bestand: {alert['material']} ({total_weight}g)")
                
                # WebSocket-Benachrichtigung
                try:
                    socketio.emit('low_stock_alert', alert)
                except Exception as emit_error:
                    scheduler_logger.warning(f"Low-Stock WebSocket-Benachrichtigung fehlgeschlagen: {emit_error}")
        
        if alerts:
            scheduler_logger.info(f"{len(alerts)} Materialien mit niedrigem Bestand gefunden")
        
        return alerts
    
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Prüfen der Materialbestände: {e}")
        return []

@with_app_context
def check_maintenance_reminders():
    """Prüft fällige Wartungsarbeiten"""
    try:
        overdue_printers = []
        urgent_printers = []
        
        printers = Printer.query.filter(
            Printer.maintenance_interval_h.isnot(None),
            Printer.maintenance_interval_h > 0
        ).all()
        
        for printer in printers:
            hours_since = (printer.total_print_hours or 0) - (printer.last_maintenance_h or 0)
            
            if hours_since >= printer.maintenance_interval_h:
                overdue_printers.append({
                    'id': printer.id,
                    'name': printer.name,
                    'hours_overdue': round(hours_since - printer.maintenance_interval_h, 1)
                })
            elif hours_since >= (printer.maintenance_interval_h * 0.9):
                hours_remaining = printer.maintenance_interval_h - hours_since
                urgent_printers.append({
                    'id': printer.id,
                    'name': printer.name,
                    'hours_remaining': round(hours_remaining, 1)
                })
        
        # Benachrichtigungen senden
        if overdue_printers:
            socketio.emit('maintenance_overdue', {
                'printers': overdue_printers,
                'count': len(overdue_printers)
            })
            scheduler_logger.warning(f"{len(overdue_printers)} Drucker haben überfällige Wartung")
        
        if urgent_printers:
            socketio.emit('maintenance_urgent', {
                'printers': urgent_printers,
                'count': len(urgent_printers)
            })
            scheduler_logger.info(f"{len(urgent_printers)} Drucker benötigen bald Wartung")
        
        return len(overdue_printers), len(urgent_printers)
    
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Prüfen der Wartungserinnerungen: {e}")
        return 0, 0

@with_app_context
def cleanup_old_logs():
    """Räumt alte Log-Einträge auf"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        # Alte Drucker-Status-Logs löschen
        old_logs_count = PrinterStatusLog.query.filter(
            PrinterStatusLog.timestamp < cutoff_date
        ).count()
        
        if old_logs_count > 0:
            PrinterStatusLog.query.filter(
                PrinterStatusLog.timestamp < cutoff_date
            ).delete()
            
            db.session.commit()
            scheduler_logger.info(f"{old_logs_count} alte Log-Einträge bereinigt")
        else:
            scheduler_logger.debug("Keine alten Logs zum Bereinigen gefunden")
    
    except Exception as e:
        scheduler_logger.error(f"Fehler bei Log-Bereinigung: {e}")
        try:
            db.session.rollback()
        except:
            pass

def add_filament_jobs(scheduler):
    """Fügt Filament-Management-Jobs hinzu"""
    try:
        # Trocknungszeiten alle 5 Minuten prüfen
        scheduler.add_job(
            func=check_drying_timers,
            trigger="interval",
            minutes=5,
            id='check_drying_timers',
            name='Trocknungszeiten prüfen',
            replace_existing=True
        )
        
        # Niedrige Bestände alle 60 Minuten prüfen  
        scheduler.add_job(
            func=check_low_filament_alerts,
            trigger="interval",
            minutes=60,
            id='check_low_filament',
            name='Niedrige Filamentbestände prüfen',
            replace_existing=True
        )
        
        scheduler_logger.info("Filament-Management-Jobs hinzugefügt")
        
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Hinzufügen der Filament-Jobs: {e}")

def add_maintenance_jobs(scheduler):
    """Fügt Wartungs-Management-Jobs hinzu"""
    try:
        # Wartungserinnerungen alle 2 Stunden prüfen
        scheduler.add_job(
            func=check_maintenance_reminders,
            trigger="interval",
            hours=2,
            id='check_maintenance_reminders',
            name='Wartungserinnerungen prüfen',
            replace_existing=True
        )
        
        scheduler_logger.info("Wartungs-Management-Jobs hinzugefügt")
        
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Hinzufügen der Wartungs-Jobs: {e}")

def get_scheduler_status():
    """Gibt detaillierte Scheduler-Informationen zurück"""
    try:
        enabled = is_scheduler_enabled()
        jobs_info = []
        
        return {
            'enabled': enabled,
            'jobs_count': len(jobs_info),
            'last_check': datetime.utcnow().isoformat()
        }
    except Exception as e:
        scheduler_logger.error(f"Fehler beim Abrufen des Scheduler-Status: {e}")
        return {'enabled': False, 'error': str(e)}

def init_scheduler(app, socketio_instance):
    """Initialisiert den Background-Scheduler"""
    # App Context für Scheduler Jobs setzen
    set_app_context(app)
    
    scheduler = BackgroundScheduler()
    
    # Logging konfigurieren
    logging.basicConfig(level=logging.INFO)
    scheduler_logger.setLevel(logging.INFO)
    
    with app.app_context():
        try:
            # Job-Completion-Check alle 30 Sekunden (wichtigste neue Funktion!)
            scheduler.add_job(
                func=check_job_completion,
                trigger="interval",
                seconds=30,
                id='check_job_completion',
                name='Jobs automatisch abschließen',
                replace_existing=True
            )
            
            # Live-Status-Broadcast alle 15 Sekunden
            scheduler.add_job(
                func=status_broadcast,
                trigger="interval",
                seconds=15,
                id='status_broadcast',
                name='Live-Status-Broadcast',
                replace_existing=True
            )
            
            # Drucker-Status-Updates alle 45 Sekunden
            scheduler.add_job(
               func=update_printer_statuses,
               trigger="interval",
               seconds=45,
               id='update_printer_statuses',
               name='Drucker-Status aktualisieren',
               replace_existing=True
            )
            
            # Job-Zuweisung alle 60 Sekunden
            scheduler.add_job(
                func=assign_pending_jobs,
                trigger="interval",
                seconds=60,
                id='assign_pending_jobs',
                name='Jobs automatisch zuweisen',
                replace_existing=True
            )
            
            # Log-Bereinigung täglich um 2:00 Uhr
            scheduler.add_job(
                func=cleanup_old_logs,
                trigger="cron",
                hour=2,
                minute=0,
                id='cleanup_old_logs',
                name='Alte Logs bereinigen',
                replace_existing=True
            )
            
            # Filament-Management-Jobs hinzufügen
            add_filament_jobs(scheduler)
            
            # Wartungs-Management-Jobs hinzufügen
            add_maintenance_jobs(scheduler)
            
            # Scheduler starten
            scheduler.start()
            
            # Herunterfahren bei App-Ende
            atexit.register(lambda: scheduler.shutdown())
            
            scheduler_logger.info("Scheduler mit allen Jobs erfolgreich gestartet")
            scheduler_logger.info(f"Aktive Jobs: {len(scheduler.get_jobs())}")
            
            # Initial Status-Check
            scheduler.add_job(
                func=lambda: scheduler_logger.info("Scheduler läuft und ist betriebsbereit"),
                trigger="interval",
                seconds=300,  # Alle 5 Minuten Status-Log
                id='scheduler_heartbeat',
                name='Scheduler Heartbeat',
                replace_existing=True
            )
            
        except Exception as e:
            scheduler_logger.error(f"Fehler beim Initialisieren des Schedulers: {e}")
    
    return scheduler