# /routes/kpi.py
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, case, desc
from extensions import db
from models import (Printer, Job, JobStatus, JobQuality, FilamentType, GCodeFile, 
                    PrinterStatusLog, PrinterStatus, MaintenanceLog, MaintenanceTaskType, 
                    FilamentSpool, User)
from datetime import datetime, timedelta
import json
from collections import defaultdict

kpi_bp = Blueprint('kpi_bp', __name__, url_prefix='/kpi')


@kpi_bp.route('/dashboard')
@login_required
def dashboard():
    # --- 1. LIVE-FARM-STATUS ---
    printer_status_counts = db.session.query(
        Printer.status,
        func.count(Printer.id)
    ).group_by(Printer.status).all()
    
    live_status = {
        'total': Printer.query.count(),
        'printing': 0,
        'idle': 0,
        'maintenance': 0,
        'offline': 0,
        'error': 0
    }
    for status, count in printer_status_counts:
        status_name = status.name if isinstance(status, PrinterStatus) else status
        live_status[status_name.lower()] = count

    pending_jobs_count = Job.query.filter(
        Job.status.in_([JobStatus.PENDING, JobStatus.QUEUED, JobStatus.ASSIGNED]),
        Job.is_archived == False
    ).count()

    # --- 2. PRODUKTIONS-ANALYSE (LETZTE 30 TAGE) ---
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    completed_jobs_query = Job.query.filter(
        Job.status == JobStatus.COMPLETED,
        Job.end_time >= thirty_days_ago
    )
    
    total_completed_30d = completed_jobs_query.count()
    successful_jobs_30d = completed_jobs_query.filter(Job.quality_assessment == JobQuality.SUCCESSFUL).count()
    failed_jobs_30d = completed_jobs_query.filter(Job.quality_assessment == JobQuality.FAILED).count()

    farm_success_rate_30d = (successful_jobs_30d / (successful_jobs_30d + failed_jobs_30d) * 100) if (successful_jobs_30d + failed_jobs_30d) > 0 else 100
    
    job_throughput_30d = total_completed_30d / 30.0

    material_trend = db.session.query(
        func.date(Job.completed_at),
        func.sum(GCodeFile.material_needed_g)
    ).join(GCodeFile, Job.gcode_file_id == GCodeFile.id)\
     .filter(Job.completed_at >= thirty_days_ago)\
     .group_by(func.date(Job.completed_at))\
     .order_by(func.date(Job.completed_at))\
     .all()
    
    material_trend_chart = {
        'labels': [datetime.strptime(d, '%Y-%m-%d').strftime('%d.%m') for d, v in material_trend if d],
        'data': [round(v, 2) for d, v in material_trend if v is not None]
    }

    # --- 3. RESSOURCEN-MANAGEMENT & PERFORMANCE ---
    
    printer_performance = db.session.query(
        Printer.name,
        func.count(Job.id).label('total_jobs'),
        func.sum(case((Job.quality_assessment == JobQuality.SUCCESSFUL, 1), else_=0)).label('successful_jobs')
    ).outerjoin(Job, Printer.id == Job.printer_id)\
     .filter(Job.status == JobStatus.COMPLETED)\
     .group_by(Printer.name)\
     .order_by(func.count(Job.id).desc())\
     .all()

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    printers = Printer.query.all()
    uptime_chart_data = {}

    for printer in printers:
        last_log_before_window = PrinterStatusLog.query.filter(
            PrinterStatusLog.printer_id == printer.id,
            PrinterStatusLog.timestamp < seven_days_ago
        ).order_by(PrinterStatusLog.timestamp.desc()).first()

        logs_in_window = PrinterStatusLog.query.filter(
            PrinterStatusLog.printer_id == printer.id,
            PrinterStatusLog.timestamp >= seven_days_ago
        ).order_by(PrinterStatusLog.timestamp.asc()).all()
        
        effective_logs = []
        initial_status = last_log_before_window.status if last_log_before_window else printer.status if printer.status else PrinterStatus.OFFLINE
        
        effective_logs.append({'status': initial_status, 'timestamp': seven_days_ago})

        for log in logs_in_window:
            if not effective_logs or log.status != effective_logs[-1]['status']:
                 effective_logs.append({'status': log.status, 'timestamp': log.timestamp})

        printer_uptime = {s.name: 0 for s in PrinterStatus}
        
        for i, log_data in enumerate(effective_logs):
            start_time = log_data['timestamp']
            
            is_last_log = (i + 1 == len(effective_logs))
            end_time = datetime.utcnow() if is_last_log else effective_logs[i + 1]['timestamp']
            
            duration_seconds = (end_time - start_time).total_seconds()
            if duration_seconds < 0: continue
            duration_hours = duration_seconds / 3600
            
            status_name = log_data['status'].name if isinstance(log_data['status'], PrinterStatus) else log_data['status']
            if status_name in printer_uptime:
                printer_uptime[status_name] += duration_hours
                
        uptime_chart_data[printer.name] = printer_uptime

    total_historical_hours = db.session.query(func.sum(Printer.historical_print_hours)).scalar() or 0
    total_new_seconds = db.session.query(func.sum(Job.actual_print_duration_s)).filter(Job.status == JobStatus.COMPLETED).scalar() or 0
    total_print_hours_all_time = round(total_historical_hours + ((total_new_seconds or 0) / 3600), 1)

    total_historical_filament = db.session.query(func.sum(Printer.historical_filament_used_g)).scalar() or 0
    total_new_filament = db.session.query(func.sum(GCodeFile.material_needed_g)).join(Job).filter(Job.status == JobStatus.COMPLETED).scalar() or 0
    total_filament_all_time = (total_historical_filament or 0) + (total_new_filament or 0)

    total_historical_jobs = db.session.query(func.sum(Printer.historical_jobs_count)).scalar() or 0
    total_new_jobs = db.session.query(func.count(Job.id)).filter(Job.status == JobStatus.COMPLETED).scalar() or 0
    total_printed_jobs_all_time = (total_historical_jobs or 0) + (total_new_jobs or 0)
    
    print_hours_per_printer = db.session.query(
        Printer.name,
        func.sum(Job.actual_print_duration_s) / 3600
    ).join(Job, Printer.id == Job.printer_id)\
     .filter(Job.status == JobStatus.COMPLETED, Job.actual_print_duration_s.isnot(None))\
     .group_by(Printer.name)\
     .order_by(desc(func.sum(Job.actual_print_duration_s)))\
     .all()
    print_hours_per_printer_chart = {
        'labels': [p[0] for p in print_hours_per_printer],
        'data': [round((p[1] or 0), 1) for p in print_hours_per_printer]
    }
    
    material_consumption_by_type = db.session.query(
        FilamentType.material_type,
        func.sum(GCodeFile.material_needed_g),
        func.max(FilamentType.color_hex)
    ).join(Job.gcode_file).join(Job.required_filament_type)\
     .filter(Job.status == JobStatus.COMPLETED)\
     .group_by(FilamentType.material_type)\
     .all()
    
    material_consumption_chart = {
        'labels': [m[0] for m in material_consumption_by_type],
        'data': [round((m[1] or 0) / 1000, 2) for m in material_consumption_by_type],
        'colors': [m[2] for m in material_consumption_by_type]
    }

    yesterday = datetime.utcnow() - timedelta(hours=24)
    recent_jobs = Job.query.filter(Job.end_time >= yesterday).order_by(Job.end_time.desc()).limit(15).all()
    recent_maintenance = MaintenanceLog.query.filter(MaintenanceLog.timestamp >= yesterday).order_by(MaintenanceLog.timestamp.desc()).limit(15).all()
    farm_activity = sorted(list(recent_jobs) + list(recent_maintenance), key=lambda x: x.end_time if hasattr(x, 'end_time') and x.end_time else (x.timestamp if hasattr(x, 'timestamp') else datetime.min), reverse=True)

    material_success = db.session.query(func.sum(GCodeFile.material_needed_g)).join(Job.gcode_file).filter(Job.quality_assessment == JobQuality.SUCCESSFUL).scalar() or 0
    material_failed = db.session.query(func.sum(GCodeFile.material_needed_g)).join(Job.gcode_file).filter(Job.quality_assessment == JobQuality.FAILED).scalar() or 0
    material_efficiency_chart = {
        'labels': ['Erfolgreich', 'Fehlgeschlagen'],
        'data': [round(material_success, 2), round(material_failed, 2)]
    }

    top_filaments = db.session.query(
        FilamentType.name,
        FilamentType.manufacturer,
        func.count(Job.id)
    ).join(Job.required_filament_type)\
     .group_by(FilamentType.name, FilamentType.manufacturer)\
     .order_by(desc(func.count(Job.id)))\
     .limit(5).all()
    
    top_filaments_chart = {
        'labels': [f"{f.manufacturer} {f.name}" for f in top_filaments],
        'data': [f[2] for f in top_filaments]
    }

    success_by_material = db.session.query(
        FilamentType.material_type,
        func.count(Job.id).label('total'),
        func.sum(case((Job.quality_assessment == JobQuality.SUCCESSFUL, 1), else_=0)).label('success')
    ).join(Job.required_filament_type)\
     .filter(Job.status == JobStatus.COMPLETED)\
     .group_by(FilamentType.material_type).all()
    
    success_rate_material_chart = {
        'labels': [s.material_type for s in success_by_material],
        'data': [round(s.success / s.total * 100, 1) if s.total > 0 else 100 for s in success_by_material]
    }

    # --- 4. BESTEHENDE KPIs ---
    weekday_map = {0: 'So', 1: 'Mo', 2: 'Di', 3: 'Mi', 4: 'Do', 5: 'Fr', 6: 'Sa'}
    jobs_by_weekday_q = db.session.query(
        func.strftime('%w', Job.completed_at).label('weekday'),
        func.count(Job.id)
    ).filter(Job.status == JobStatus.COMPLETED, Job.completed_at.isnot(None))\
     .group_by('weekday').all()
    jobs_by_weekday = {int(day): count for day, count in jobs_by_weekday_q if day is not None}
    jobs_by_weekday_chart = {
        'labels': [weekday_map[i] for i in range(1, 7)] + [weekday_map[0]],
        'data': [jobs_by_weekday.get(i, 0) for i in range(1, 7)] + [jobs_by_weekday.get(0, 0)]
    }

    avg_times = db.session.query(
        func.avg(Job.preparation_time_min),
        func.avg(Job.post_processing_time_min)
    ).filter(Job.status == JobStatus.COMPLETED).one()
    avg_job_times_chart = {
        'labels': ['Vorbereitung', 'Nachbearbeitung'],
        'data': [round(t or 0, 1) for t in avg_times]
    }
    
    maintenance_by_type = db.session.query(
        MaintenanceLog.task_type,
        func.count(MaintenanceLog.id)
    ).group_by(MaintenanceLog.task_type).all()
    maintenance_by_type_chart = {
        'labels': [m[0].value for m in maintenance_by_type],
        'data': [m[1] for m in maintenance_by_type]
    }

    stock_by_material = db.session.query(
        FilamentType.material_type,
        func.sum(FilamentSpool.current_weight_g) / 1000
    ).join(FilamentSpool).group_by(FilamentType.material_type).all()
    stock_by_material_chart = {
        'labels': [s[0] for s in stock_by_material],
        'data': [round(s[1] or 0, 2) for s in stock_by_material]
    }

    daily_jobs_30d = db.session.query(
        func.date(Job.completed_at).label('day'),
        func.sum(case((Job.quality_assessment == JobQuality.SUCCESSFUL, 1), else_=0)).label('successful'),
        func.sum(case((Job.quality_assessment == JobQuality.FAILED, 1), else_=0)).label('failed')
    ).filter(Job.completed_at >= thirty_days_ago, Job.status == JobStatus.COMPLETED)\
     .group_by('day').order_by('day').all()
    
    production_trend_chart = {
        'labels': [datetime.strptime(d.day, '%Y-%m-%d').strftime('%d.%m') for d in daily_jobs_30d],
        'successful': [d.successful for d in daily_jobs_30d],
        'failed': [d.failed for d in daily_jobs_30d]
    }

    costs_per_printer = db.session.query(
        Printer.name,
        func.sum(Job.total_cost)
    ).join(Job, Printer.id == Job.printer_id)\
     .filter(Job.total_cost.isnot(None))\
     .group_by(Printer.name)\
     .order_by(desc(func.sum(Job.total_cost))).all()
    costs_per_printer_chart = {
        'labels': [p[0] for p in costs_per_printer],
        'data': [round(p[1] or 0, 2) for p in costs_per_printer]
    }

    avg_duration_success = db.session.query(func.avg(Job.actual_print_duration_s)).filter(Job.quality_assessment == JobQuality.SUCCESSFUL, Job.actual_print_duration_s.isnot(None)).scalar() or 0
    avg_duration_failed = db.session.query(func.avg(Job.actual_print_duration_s)).filter(Job.quality_assessment == JobQuality.FAILED, Job.actual_print_duration_s.isnot(None)).scalar() or 0

    total_costs = db.session.query(
        func.sum(Job.material_cost),
        func.sum(Job.machine_cost),
        func.sum(Job.personnel_cost)
    ).filter(Job.status == JobStatus.COMPLETED).first()
    
    cost_chart_data = {
        'labels': ['Material', 'Maschine', 'Personal'],
        'data': [round(c or 0, 2) for c in total_costs]
    }

    failures_by_material = db.session.query(
        FilamentType.name,
        func.count(Job.id)
    ).join(Job.required_filament_type)\
     .filter(Job.quality_assessment == JobQuality.FAILED)\
     .group_by(FilamentType.name)\
     .order_by(func.count(Job.id).desc()).all()
     
    failures_by_material_chart = {
        'labels': [m[0] for m in failures_by_material],
        'data': [m[1] for m in failures_by_material]
    }
    
    filament_stock = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()

    # --- 5. PERFORMANCE & EFFIZIENZ (NEU) ---
    
    # OEE-Berechnung (vereinfacht)
    total_available_time = Printer.query.count() * 7 * 24  # Stunden in 7 Tagen
    total_actual_print_time = sum([sum(p.values()) for p in uptime_chart_data.values()])
    availability = (total_actual_print_time / total_available_time * 100) if total_available_time > 0 else 0
    
    performance = 85  # Vereinfachte Annahme - könnte durch Soll vs. Ist-Druckzeit berechnet werden
    quality_rate = farm_success_rate_30d
    
    oee_score = (availability * performance * quality_rate) / 10000
    
    oee_components_chart = {
        'labels': ['Verfügbarkeit', 'Leistung', 'Qualität'],
        'data': [round(availability, 1), round(performance, 1), round(quality_rate, 1)]
    }
    
    # MTBF & MTTR (Mean Time Between/To Repair)
    failed_jobs = Job.query.filter(Job.quality_assessment == JobQuality.FAILED).all()
    if len(failed_jobs) > 1:
        time_between_failures = []
        for i in range(len(failed_jobs) - 1):
            if failed_jobs[i].end_time and failed_jobs[i+1].start_time:
                delta = (failed_jobs[i+1].start_time - failed_jobs[i].end_time).total_seconds() / 3600
                time_between_failures.append(delta)
        mtbf_hours = sum(time_between_failures) / len(time_between_failures) if time_between_failures else 0
    else:
        mtbf_hours = total_print_hours_all_time
    
    mttr_hours = (avg_duration_failed / 60) if avg_duration_failed > 0 else 0
    
    # Kapazitätsauslastung über Zeit
    capacity_utilization_data = []
    for i in range(7):
        day_start = datetime.utcnow() - timedelta(days=7-i)
        day_end = day_start + timedelta(days=1)
        
        day_print_time = db.session.query(func.sum(Job.actual_print_duration_s)).filter(
            Job.start_time >= day_start,
            Job.start_time < day_end,
            Job.status == JobStatus.COMPLETED
        ).scalar() or 0
        
        day_capacity = Printer.query.count() * 24 * 3600
        utilization = (day_print_time / day_capacity * 100) if day_capacity > 0 else 0
        capacity_utilization_data.append(round(utilization, 1))
    
    capacity_chart = {
        'labels': [(datetime.utcnow() - timedelta(days=7-i)).strftime('%d.%m') for i in range(7)],
        'data': capacity_utilization_data
    }
    
    # Durchlaufzeiten
    completed_jobs_with_times = Job.query.filter(
        Job.status == JobStatus.COMPLETED,
        Job.start_time.isnot(None),
        Job.end_time.isnot(None),
        Job.created_at.isnot(None)
    ).order_by(Job.end_time.desc()).limit(20).all()
    
    lead_times = []
    for job in completed_jobs_with_times:
        lead_time_hours = (job.end_time - job.created_at).total_seconds() / 3600
        lead_times.append({
            'name': job.name[:15],
            'lead_time': round(lead_time_hours, 1)
        })
    
    lead_time_chart = {
        'labels': [lt['name'] for lt in lead_times],
        'data': [lt['lead_time'] for lt in lead_times]
    }
    
    avg_lead_time = sum([lt['lead_time'] for lt in lead_times]) / len(lead_times) if lead_times else 0
    
    # First Pass Yield
    total_reviewed = Job.query.filter(
        Job.quality_assessment.in_([JobQuality.SUCCESSFUL, JobQuality.FAILED])
    ).count()
    first_pass_yield = (successful_jobs_30d / total_reviewed * 100) if total_reviewed > 0 else 100

    # --- 6. KOSTEN & ROI (NEU) ---
    
    # Kostenstruktur
    cost_breakdown_chart = {
        'labels': ['Material', 'Maschine', 'Personal'],
        'data': [round(c or 0, 2) for c in total_costs],
        'percentages': []
    }
    total_cost_sum = sum([c or 0 for c in total_costs])
    if total_cost_sum > 0:
        cost_breakdown_chart['percentages'] = [round((c or 0) / total_cost_sum * 100, 1) for c in total_costs]
    
    # Kosten pro Teil
    cost_per_part = (total_cost_sum / total_completed_30d) if total_completed_30d > 0 else 0
    
    # Energiekosten (geschätzt)
    energy_costs_data = []
    for printer in printers:
        if printer.power_consumption_w and printer.energy_price_kwh:
            printer_hours = print_hours_per_printer_chart['data'][print_hours_per_printer_chart['labels'].index(printer.name)] if printer.name in print_hours_per_printer_chart['labels'] else 0
            # Konvertiere alle Werte zu float um Decimal-Fehler zu vermeiden
            power_w = float(printer.power_consumption_w)
            price_kwh = float(printer.energy_price_kwh)
            hours = float(printer_hours)
            energy_cost = (power_w / 1000) * hours * price_kwh
            energy_costs_data.append({
                'printer': printer.name,
                'cost': round(energy_cost, 2)
            })
    
    energy_costs_chart = {
        'labels': [e['printer'] for e in energy_costs_data],
        'data': [e['cost'] for e in energy_costs_data]
    }
    
    # ROI-Berechnung pro Drucker
    roi_data = []
    for printer in printers:
        if printer.purchase_cost and printer.purchase_cost > 0:
            printer_total_cost = db.session.query(func.sum(Job.total_cost)).filter(
                Job.printer_id == printer.id,
                Job.status == JobStatus.COMPLETED
            ).scalar() or 0
            
            roi = ((printer_total_cost - printer.purchase_cost) / printer.purchase_cost * 100) if printer.purchase_cost > 0 else 0
            roi_data.append({
                'printer': printer.name,
                'roi': round(roi, 1)
            })
    
    roi_chart = {
        'labels': [r['printer'] for r in roi_data],
        'data': [r['roi'] for r in roi_data]
    }
    
    # Monatliche Kostenentwicklung
    monthly_costs = db.session.query(
        func.strftime('%Y-%m', Job.completed_at).label('month'),
        func.sum(Job.total_cost)
    ).filter(
        Job.completed_at >= thirty_days_ago,
        Job.status == JobStatus.COMPLETED
    ).group_by('month').order_by('month').all()
    
    monthly_costs_chart = {
        'labels': [datetime.strptime(m[0], '%Y-%m').strftime('%B') if m[0] else '' for m in monthly_costs],
        'data': [round(m[1] or 0, 2) for m in monthly_costs]
    }
    
    # Wartungskosten vs. Produktionskosten
    total_maintenance_cost = sum([p.annual_maintenance_cost or 0 for p in printers])
    maintenance_vs_production_chart = {
        'labels': ['Produktionskosten', 'Wartungskosten (geschätzt)'],
        'data': [round(total_cost_sum, 2), round(total_maintenance_cost / 12, 2)]
    }

    return render_template(
        'kpi/dashboard.html',
        # Bestehende Daten
        live_status=live_status,
        pending_jobs_count=pending_jobs_count,
        farm_success_rate_30d=round(farm_success_rate_30d, 1),
        job_throughput_30d=round(job_throughput_30d, 1),
        material_trend_chart=material_trend_chart,
        printer_performance=printer_performance,
        uptime_chart_data=uptime_chart_data,
        filament_stock=filament_stock,
        avg_duration_success_min=round(avg_duration_success / 60),
        avg_duration_failed_min=round(avg_duration_failed / 60),
        cost_chart_data=cost_chart_data,
        failures_by_material_chart=failures_by_material_chart,
        total_print_hours_all_time=total_print_hours_all_time,
        total_filament_all_time_kg=round(total_filament_all_time / 1000, 2),
        total_printed_jobs_all_time=total_printed_jobs_all_time,
        print_hours_per_printer_chart=print_hours_per_printer_chart,
        material_consumption_chart=material_consumption_chart,
        farm_activity=farm_activity,
        material_efficiency_chart=material_efficiency_chart,
        top_filaments_chart=top_filaments_chart,
        success_rate_material_chart=success_rate_material_chart,
        jobs_by_weekday_chart=jobs_by_weekday_chart,
        avg_job_times_chart=avg_job_times_chart,
        maintenance_by_type_chart=maintenance_by_type_chart,
        stock_by_material_chart=stock_by_material_chart,
        production_trend_chart=production_trend_chart,
        costs_per_printer_chart=costs_per_printer_chart,
        # Neue Performance-Daten
        oee_score=round(oee_score, 1),
        oee_components_chart=oee_components_chart,
        mtbf_hours=round(mtbf_hours, 1),
        mttr_hours=round(mttr_hours, 1),
        availability=round(availability, 1),
        capacity_chart=capacity_chart,
        lead_time_chart=lead_time_chart,
        avg_lead_time=round(avg_lead_time, 1),
        first_pass_yield=round(first_pass_yield, 1),
        # Neue Kosten/ROI-Daten
        cost_breakdown_chart=cost_breakdown_chart,
        cost_per_part=round(cost_per_part, 2),
        energy_costs_chart=energy_costs_chart,
        roi_chart=roi_chart,
        monthly_costs_chart=monthly_costs_chart,
        maintenance_vs_production_chart=maintenance_vs_production_chart,
        total_cost_sum=round(total_cost_sum, 2)
    )