# routes/maintenance_new.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from extensions import db
from models import (
    MaintenanceTaskNew, MaintenanceScheduleNew, MaintenanceExecutionNew,
    MaintenanceStatus, MaintenancePriority, MaintenanceInterval,
    MaintenanceTaskCategory, Printer, Consumable, User,
    TaskConsumableNew, ExecutionConsumableNew, MaintenancePhotoNew
)
import datetime
import qrcode
import io
import os
from werkzeug.utils import secure_filename
from sqlalchemy import and_, or_

maintenance_new_bp = Blueprint('maintenance_new_bp', __name__, url_prefix='/maintenance-v2')

@maintenance_new_bp.route('/')
@login_required
def dashboard():
    """Hauptübersicht aller Wartungen"""
    # Überfällige Wartungen
    overdue = MaintenanceScheduleNew.query.filter_by(status=MaintenanceStatus.OVERDUE).count()
    
    # Heute fällige
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0)
    today_end = today_start + datetime.timedelta(days=1)
    due_today = MaintenanceScheduleNew.query.filter(
        and_(
            MaintenanceScheduleNew.status == MaintenanceStatus.SCHEDULED,
            MaintenanceScheduleNew.scheduled_date >= today_start,
            MaintenanceScheduleNew.scheduled_date < today_end
        )
    ).count()
    
    # Diese Woche
    week_end = today_start + datetime.timedelta(days=7)
    due_this_week = MaintenanceScheduleNew.query.filter(
        and_(
            MaintenanceScheduleNew.status == MaintenanceStatus.SCHEDULED,
            MaintenanceScheduleNew.scheduled_date >= today_start,
            MaintenanceScheduleNew.scheduled_date < week_end
        )
    ).count()
    
    # In Bearbeitung
    in_progress = MaintenanceScheduleNew.query.filter_by(status=MaintenanceStatus.IN_PROGRESS).count()
    
    # Letzte Wartungen
    recent_executions = MaintenanceExecutionNew.query.filter(
        MaintenanceExecutionNew.completed_at.isnot(None)
    ).order_by(MaintenanceExecutionNew.completed_at.desc()).limit(10).all()
    
    # Anstehende Wartungen (nächste 30 Tage)
    upcoming = MaintenanceScheduleNew.query.filter(
        and_(
            MaintenanceScheduleNew.status.in_([MaintenanceStatus.SCHEDULED, MaintenanceStatus.OVERDUE]),
            MaintenanceScheduleNew.scheduled_date < today_start + datetime.timedelta(days=30)
        )
    ).order_by(MaintenanceScheduleNew.scheduled_date).limit(20).all()
    
    return render_template('maintenance_v2/dashboard.html',
                         overdue=overdue,
                         due_today=due_today,
                         due_this_week=due_this_week,
                         in_progress=in_progress,
                         recent_executions=recent_executions,
                         upcoming=upcoming)

@maintenance_new_bp.route('/tasks')
@login_required
def tasks():
    """Verwaltung von Wartungsaufgaben-Templates"""
    all_tasks = MaintenanceTaskNew.query.order_by(MaintenanceTaskNew.category, MaintenanceTaskNew.title).all()
    printers = Printer.query.order_by(Printer.name).all()
    consumables = Consumable.query.order_by(Consumable.name).all()
    
    return render_template('maintenance_v2/tasks.html',
                         tasks=all_tasks,
                         printers=printers,
                         consumables=consumables,
                         categories=MaintenanceTaskCategory,
                         intervals=MaintenanceInterval,
                         priorities=MaintenancePriority)

@maintenance_new_bp.route('/tasks/add', methods=['POST'])
@login_required
def add_task():
    """Neue Wartungsaufgabe erstellen"""
    try:
        task = MaintenanceTaskNew(
            title=request.form['title'],
            description=request.form.get('description'),
            category=MaintenanceTaskCategory[request.form['category']],
            interval_type=MaintenanceInterval[request.form.get('interval_type', 'MANUAL')],
            interval_value=int(request.form['interval_value']) if request.form.get('interval_value') else None,
            priority=MaintenancePriority[request.form.get('priority', 'MEDIUM')],
            estimated_duration_min=int(request.form['estimated_duration_min']) if request.form.get('estimated_duration_min') else None,
            instruction_url=request.form.get('instruction_url'),
            video_tutorial_url=request.form.get('video_tutorial_url'),
            applicable_to_all=bool(request.form.get('applicable_to_all'))
        )
        
        # Checkliste verarbeiten
        checklist_text = request.form.get('checklist_items', '')
        if checklist_text:
            task.checklist_items = [item.strip() for item in checklist_text.split('\n') if item.strip()]
        
        # Sicherheitshinweise
        safety_text = request.form.get('safety_warnings', '')
        if safety_text:
            task.safety_warnings = [item.strip() for item in safety_text.split('\n') if item.strip()]
        
        # Drucker zuweisen
        if not task.applicable_to_all:
            printer_ids = request.form.getlist('printer_ids')
            task.applicable_printers = Printer.query.filter(Printer.id.in_(printer_ids)).all()
        
        # Verbrauchsmaterialien zuweisen
        consumable_ids = request.form.getlist('consumable_ids[]')
        quantities = request.form.getlist('consumable_quantities[]')
        
        for cons_id, qty in zip(consumable_ids, quantities):
            if cons_id and qty:
                tc = TaskConsumableNew(
                    consumable_id=int(cons_id),
                    quantity=int(qty)
                )
                task.required_consumables.append(tc)
        
        db.session.add(task)
        db.session.commit()
        
        flash(f'Wartungsaufgabe "{task.title}" erfolgreich erstellt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Erstellen: {e}', 'danger')
    
    return redirect(url_for('maintenance_new_bp.tasks'))

@maintenance_new_bp.route('/schedule/<int:printer_id>')
@login_required
def printer_schedule(printer_id):
    """Wartungsplan für einen spezifischen Drucker"""
    printer = db.session.get(Printer, printer_id)
    if not printer:
        flash('Drucker nicht gefunden.', 'danger')
        return redirect(url_for('maintenance_new_bp.dashboard'))
    
    schedules = MaintenanceScheduleNew.query.filter_by(printer_id=printer_id).order_by(MaintenanceScheduleNew.scheduled_date).all()
    executions = MaintenanceExecutionNew.query.filter_by(printer_id=printer_id).order_by(MaintenanceExecutionNew.completed_at.desc()).limit(20).all()
    
    return render_template('maintenance_v2/printer_schedule.html',
                         printer=printer,
                         schedules=schedules,
                         executions=executions)

@maintenance_new_bp.route('/execute/<int:schedule_id>')
@login_required
def execute_maintenance(schedule_id):
    """Wartung durchführen"""
    schedule = db.session.get(MaintenanceScheduleNew, schedule_id)
    if not schedule:
        flash('Wartungsplan nicht gefunden.', 'danger')
        return redirect(url_for('maintenance_new_bp.dashboard'))
    
    return render_template('maintenance_v2/execute.html', schedule=schedule)

@maintenance_new_bp.route('/execute/<int:schedule_id>/start', methods=['POST'])
@login_required
def start_execution(schedule_id):
    """Wartung starten"""
    schedule = db.session.get(MaintenanceScheduleNew, schedule_id)
    if not schedule:
        return jsonify({'status': 'error', 'message': 'Nicht gefunden'}), 404
    
    execution = MaintenanceExecutionNew(
        schedule_id=schedule_id,
        task_id=schedule.task_id,
        printer_id=schedule.printer_id,
        performed_by_id=current_user.id,
        started_at=datetime.datetime.utcnow()
    )
    
    schedule.status = MaintenanceStatus.IN_PROGRESS
    schedule.printer.status = models.PrinterStatus.MAINTENANCE
    
    db.session.add(execution)
    db.session.commit()
    
    return jsonify({'status': 'success', 'execution_id': execution.id})

@maintenance_new_bp.route('/execute/<int:execution_id>/complete', methods=['POST'])
@login_required
def complete_execution(execution_id):
    """Wartung abschließen"""
    execution = db.session.get(MaintenanceExecutionNew, execution_id)
    if not execution:
        return jsonify({'status': 'error', 'message': 'Nicht gefunden'}), 404
    
    data = request.get_json()
    
    execution.completed_at = datetime.datetime.utcnow()
    execution.actual_duration_min = int((execution.completed_at - execution.started_at).total_seconds() / 60)
    execution.checklist_results = data.get('checklist_results', [])
    execution.issues_found = data.get('issues_found')
    execution.recommendations = data.get('recommendations')
    execution.notes = data.get('notes')
    execution.labor_cost = data.get('labor_cost')
    execution.parts_cost = data.get('parts_cost')
    execution.total_cost = (execution.labor_cost or 0) + (execution.parts_cost or 0)
    
    # Verbrauchsmaterialien verarbeiten
    for item in data.get('used_consumables', []):
        consumable = db.session.get(Consumable, item['consumable_id'])
        if consumable:
            consumable.stock_level = max(0, consumable.stock_level - item['quantity'])
            
            ec = ExecutionConsumableNew(
                execution_id=execution_id,
                consumable_id=item['consumable_id'],
                quantity_used=item['quantity']
            )
            db.session.add(ec)
    
    # Schedule abschließen
    if execution.schedule:
        execution.schedule.status = MaintenanceStatus.COMPLETED
    
    # Drucker-Status zurücksetzen
    execution.printer.status = models.PrinterStatus.IDLE
    execution.printer.last_maintenance_date = datetime.date.today()
    execution.printer.last_maintenance_h = execution.printer.total_print_hours
    
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Wartung abgeschlossen'})

@maintenance_new_bp.route('/qr/<int:printer_id>')
@login_required
def generate_qr(printer_id):
    """QR-Code für Drucker-Wartung generieren"""
    printer = db.session.get(Printer, printer_id)
    if not printer:
        return "Drucker nicht gefunden", 404
    
    # URL zur Wartungsseite
    url = url_for('maintenance_new_bp.printer_schedule', printer_id=printer_id, _external=True)
    
    # QR-Code erstellen
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # In Memory speichern
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@maintenance_new_bp.route('/history')
@login_required
def history():
    """Wartungsverlauf"""
    printer_id = request.args.get('printer_id', type=int)
    
    query = MaintenanceExecutionNew.query.filter(MaintenanceExecutionNew.completed_at.isnot(None))
    
    if printer_id:
        query = query.filter_by(printer_id=printer_id)
    
    executions = query.order_by(MaintenanceExecutionNew.completed_at.desc()).all()
    printers = Printer.query.order_by(Printer.name).all()
    
    return render_template('maintenance_v2/history.html',
                         executions=executions,
                         printers=printers,
                         selected_printer=printer_id)



@maintenance_new_bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """Wartungsaufgabe löschen"""
    task = db.session.get(MaintenanceTaskNew, task_id)
    if task:
        try:
            db.session.delete(task)
            db.session.commit()
            flash(f'Wartungsaufgabe "{task.title}" wurde gelöscht.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Löschen: {e}', 'danger')
    
    return redirect(url_for('maintenance_new_bp.tasks'))

@maintenance_new_bp.route('/schedule/<int:printer_id>/add', methods=['POST'])
@login_required
def schedule_task(printer_id):
    """Neue Wartung planen"""
    try:
        schedule = MaintenanceScheduleNew(
            task_id=int(request.form['task_id']),
            printer_id=printer_id,
            scheduled_date=datetime.datetime.strptime(request.form['scheduled_date'], '%Y-%m-%dT%H:%M'),
            due_date=datetime.datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form.get('due_date') else None,
            assigned_to_user_id=int(request.form['assigned_to_user_id']) if request.form.get('assigned_to_user_id') else None,
            notes=request.form.get('notes')
        )
        
        # Priorität von Task übernehmen
        schedule.priority = schedule.task.priority
        
        db.session.add(schedule)
        db.session.commit()
        
        flash('Wartung erfolgreich geplant.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Planen: {e}', 'danger')
    
    return redirect(url_for('maintenance_new_bp.printer_schedule', printer_id=printer_id))

@maintenance_new_bp.route('/export/ical')
@login_required
def export_ical():
    """Wartungsplan als iCal exportieren"""
    from icalendar import Calendar, Event
    
    cal = Calendar()
    cal.add('prodid', '-//3D Print Farm Maintenance//DE')
    cal.add('version', '2.0')
    
    schedules = MaintenanceScheduleNew.query.filter(
        MaintenanceScheduleNew.status.in_([MaintenanceStatus.SCHEDULED, MaintenanceStatus.OVERDUE])
    ).all()
    
    for schedule in schedules:
        event = Event()
        event.add('summary', f'Wartung: {schedule.task.title} - {schedule.printer.name}')
        event.add('dtstart', schedule.scheduled_date)
        event.add('dtend', schedule.scheduled_date + datetime.timedelta(minutes=schedule.task.estimated_duration_min or 60))
        event.add('description', schedule.task.description or '')
        event.add('location', schedule.printer.location or '')
        
        cal.add_component(event)
    
    response = make_response(cal.to_ical())
    response.headers['Content-Type'] = 'text/calendar'
    response.headers['Content-Disposition'] = 'attachment; filename=wartungsplan.ics'
    
    return response