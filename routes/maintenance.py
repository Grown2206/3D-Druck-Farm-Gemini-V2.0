# routes/maintenance.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from models import (
    MaintenanceTaskDefinition, MaintenanceTaskCategory, 
    Consumable, Printer, MaintenanceLog
)
from flask_login import login_required
from .forms import update_model_from_form

maintenance_bp = Blueprint('maintenance_bp', __name__)

@maintenance_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """Hauptseite für Wartungsaufgaben-Definitionen"""
    if request.method == 'POST':
        title = request.form.get('title')
        if not title:
            flash("Ein Titel ist für die Aufgabe erforderlich.", "danger")
        else:
            try:
                new_task = MaintenanceTaskDefinition(title=title)
                field_map = {
                    'description': ('description', str),
                    'category': ('category', MaintenanceTaskCategory),
                    'interval_hours': ('interval_hours', int),
                    'is_active': ('is_active', bool),
                    'instruction_url': ('instruction_url', str),
                    'required_consumable_id': ('required_consumable_id', int),
                    'required_consumable_quantity': ('required_consumable_quantity', int),
                }
                update_model_from_form(new_task, request.form, field_map)

                db.session.add(new_task)
                db.session.commit()
                flash(f"Wartungsaufgabe '{title}' erfolgreich erstellt.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Fehler beim Erstellen der Aufgabe: {e}", "danger")
        return redirect(url_for('maintenance_bp.index'))

    tasks = MaintenanceTaskDefinition.query.order_by(
        MaintenanceTaskDefinition.category, 
        MaintenanceTaskDefinition.title
    ).all()
    consumables = Consumable.query.order_by(Consumable.name).all()
    
    return render_template('maintenance/index.html', 
                           tasks=tasks, 
                           consumables=consumables,
                           MaintenanceTaskCategory=MaintenanceTaskCategory,
                           task_to_edit=None)

@maintenance_bp.route('/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """Bearbeite eine Wartungsaufgaben-Definition"""
    task = db.session.get(MaintenanceTaskDefinition, task_id)
    if not task:
        flash("Aufgabe nicht gefunden.", "danger")
        return redirect(url_for('maintenance_bp.index'))

    if request.method == 'POST':
        title = request.form.get('title')
        if not title:
            flash("Ein Titel ist für die Aufgabe erforderlich.", "danger")
        else:
            try:
                field_map = {
                    'title': ('title', str),
                    'description': ('description', str),
                    'category': ('category', MaintenanceTaskCategory),
                    'interval_hours': ('interval_hours', int),
                    'is_active': ('is_active', bool),
                    'instruction_url': ('instruction_url', str),
                    'required_consumable_id': ('required_consumable_id', int),
                    'required_consumable_quantity': ('required_consumable_quantity', int),
                }
                update_model_from_form(task, request.form, field_map)
                db.session.commit()
                flash(f"Wartungsaufgabe '{task.title}' erfolgreich aktualisiert.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Fehler beim Aktualisieren: {e}", "danger")
        return redirect(url_for('maintenance_bp.index'))
    
    tasks = MaintenanceTaskDefinition.query.order_by(
        MaintenanceTaskDefinition.category, 
        MaintenanceTaskDefinition.title
    ).all()
    consumables = Consumable.query.order_by(Consumable.name).all()
    
    return render_template('maintenance/index.html', 
                           tasks=tasks, 
                           consumables=consumables,
                           MaintenanceTaskCategory=MaintenanceTaskCategory,
                           task_to_edit=task)

@maintenance_bp.route('/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    """Lösche eine Wartungsaufgaben-Definition"""
    task = db.session.get(MaintenanceTaskDefinition, task_id)
    if task:
        try:
            db.session.delete(task)
            db.session.commit()
            flash(f"Wartungsaufgabe '{task.title}' wurde gelöscht.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Löschen: {e}", "danger")
    else:
        flash("Aufgabe nicht gefunden.", "danger")
    return redirect(url_for('maintenance_bp.index'))

@maintenance_bp.route('/schedule')
@login_required
def schedule():
    """Zeigt anstehende Wartungsaufgaben für alle Drucker"""
    printers = Printer.query.all()
    
    maintenance_schedule = []
    for printer in printers:
        active_tasks = MaintenanceTaskDefinition.query.filter_by(is_active=True).all()
        
        for task in active_tasks:
            if task.interval_hours:
                hours_since_last = (printer.total_print_hours or 0) - (printer.last_maintenance_h or 0)
                hours_remaining = task.interval_hours - hours_since_last
                
                if hours_remaining <= 0:
                    urgency = 'overdue'
                    urgency_text = 'Überfällig'
                elif hours_remaining <= 10:
                    urgency = 'urgent'
                    urgency_text = 'Dringend'
                elif hours_remaining <= 50:
                    urgency = 'soon'
                    urgency_text = 'Bald fällig'
                else:
                    urgency = 'ok'
                    urgency_text = 'OK'
                
                maintenance_schedule.append({
                    'printer': printer,
                    'task': task,
                    'hours_remaining': hours_remaining,
                    'urgency': urgency,
                    'urgency_text': urgency_text
                })
    
    maintenance_schedule.sort(key=lambda x: x['hours_remaining'])
    
    return render_template('maintenance/schedule.html', 
                         maintenance_schedule=maintenance_schedule)

@maintenance_bp.route('/history')
@login_required
def history():
    """Zeigt den vollständigen Wartungsverlauf"""
    printer_id = request.args.get('printer_id', type=int)
    
    query = MaintenanceLog.query
    if printer_id:
        query = query.filter_by(printer_id=printer_id)
    
    logs = query.order_by(MaintenanceLog.timestamp.desc()).all()
    printers = Printer.query.order_by(Printer.name).all()
    
    return render_template('maintenance/history.html', 
                         logs=logs, 
                         printers=printers,
                         selected_printer=printer_id)