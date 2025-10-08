from models import Printer, Job, JobStatus, PrinterStatus, FilamentSpool
from extensions import db
import datetime

def find_best_printer_for_job(job):
    """
    Findet den optimalen, verfügbaren Drucker für einen gegebenen Job.
    Kriterien:
    1. Drucker muss IDLE sein.
    2. Drucker muss das benötigte Material unterstützen.
    3. Drucker muss die benötigte Spule geladen haben (falls eine Spule geladen ist).
    4. Drucker mit der geringsten Anzahl an anstehenden Aufträgen wird bevorzugt.
    """
    idle_printers = Printer.query.filter_by(status=PrinterStatus.IDLE).all()
    
    if not idle_printers:
        return None # Kein Drucker ist frei

    compatible_printers = []
    
    # KORREKTUR: Verwende die neuen Attribute aus dem Job-Modell
    if job.required_filament_type_id and job.required_filament_type:
        required_material_type = job.required_filament_type.material_type.upper()
        
        for printer in idle_printers:
            compatible_types = [pt.strip().upper() for pt in printer.compatible_material_types.split(',')]
            if required_material_type in compatible_types:
                compatible_printers.append(printer)
    else:
        # Wenn kein Material-Typ für den Job spezifiziert ist, sind alle freien Drucker kompatibel
        compatible_printers = idle_printers

    if not compatible_printers:
        return None # Kein freier Drucker unterstützt das Material

    # Kriterium 3: Geladene Spule
    printers_with_correct_spool = []
    if job.required_filament_type_id:
        for printer in compatible_printers:
            active_spool = printer.assigned_spools.filter_by(is_in_use=True).first()
            # KORREKTUR: Vergleiche mit der korrekten ID
            if active_spool and active_spool.filament_type_id == job.required_filament_type_id:
                # Perfekter Match: Drucker ist frei, Material passt, Spule ist bereits geladen
                printers_with_correct_spool.append(printer)

    # Wenn Drucker mit der richtigen Spule gefunden wurden, bevorzuge diese
    if printers_with_correct_spool:
        target_printers = printers_with_correct_spool
    else:
        # Ansonsten nimm alle kompatiblen Drucker, die keine Spule geladen haben
        printers_without_spool = [p for p in compatible_printers if not p.assigned_spools.filter_by(is_in_use=True).first()]
        if printers_without_spool:
            target_printers = printers_without_spool
        else:
            # Wenn alle kompatiblen Drucker eine (falsche) Spule geladen haben, nimm einen von ihnen.
            target_printers = compatible_printers

    # Kriterium 4: Geringste Auslastung (Anzahl an Queued/Assigned Jobs)
    if not target_printers:
        return None

    best_printer = min(target_printers, key=lambda p: p.jobs.filter(Job.status.in_([JobStatus.QUEUED, JobStatus.ASSIGNED])).count())
    
    return best_printer