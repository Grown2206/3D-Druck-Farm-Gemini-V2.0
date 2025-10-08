# routes/todo.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from extensions import db
from models import ToDo, User, ToDoCategory, ToDoStatus
from flask_login import login_required, current_user
from .forms import update_model_from_form
import datetime
import csv
import io

todo_bp = Blueprint('todo_bp', __name__)

@todo_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        description = request.form.get('description')
        if not description:
            flash("Eine Beschreibung ist erforderlich.", "danger")
        else:
            try:
                new_todo = ToDo(description=description, created_by_id=current_user.id)
                
                field_map = {
                    'category': ('category', ToDoCategory),
                    'status': ('status', ToDoStatus),
                    'end_date': ('end_date', lambda d: datetime.datetime.strptime(d, '%Y-%m-%d').date() if d else None),
                    'assigned_to_id': ('assigned_to_id', int),
                    'notes': ('notes', str)
                }
                update_model_from_form(new_todo, request.form, field_map)

                db.session.add(new_todo)
                db.session.commit()
                flash("Neue Aufgabe erfolgreich erstellt.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Fehler beim Erstellen der Aufgabe: {e}", "danger")
        return redirect(url_for('todo_bp.index'))

    # Daten für die Anzeige
    users = User.query.order_by(User.username).all()
    todos = ToDo.query.order_by(ToDo.start_date.desc()).all()
    return render_template('todo/index.html', todos=todos, users=users, ToDoCategory=ToDoCategory, ToDoStatus=ToDoStatus)

@todo_bp.route('/edit/<int:todo_id>', methods=['GET', 'POST'])
@login_required
def edit_todo(todo_id):
    todo = db.session.get(ToDo, todo_id)
    if not todo:
        flash("Aufgabe nicht gefunden.", "danger")
        return redirect(url_for('todo_bp.index'))

    if request.method == 'POST':
        description = request.form.get('description')
        if not description:
            flash("Eine Beschreibung ist erforderlich.", "danger")
        else:
            try:
                field_map = {
                    'description': ('description', str),
                    'category': ('category', ToDoCategory),
                    'status': ('status', ToDoStatus),
                    'end_date': ('end_date', lambda d: datetime.datetime.strptime(d, '%Y-%m-%d').date() if d else None),
                    'assigned_to_id': ('assigned_to_id', int),
                    'notes': ('notes', str)
                }
                update_model_from_form(todo, request.form, field_map)
                
                if todo.end_date and todo.status == ToDoStatus.OPEN:
                    todo.status = ToDoStatus.IN_PROGRESS

                db.session.commit()
                flash(f"Aufgabe erfolgreich aktualisiert.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Fehler beim Aktualisieren der Aufgabe: {e}", "danger")
        return redirect(url_for('todo_bp.index'))
    
    # GET Request: Zeige das Bearbeitungsformular an
    users = User.query.order_by(User.username).all()
    return render_template('todo/edit.html', todo=todo, users=users, ToDoCategory=ToDoCategory, ToDoStatus=ToDoStatus)


@todo_bp.route('/delete/<int:todo_id>', methods=['POST'])
@login_required
def delete_todo(todo_id):
    todo = db.session.get(ToDo, todo_id)
    if todo:
        try:
            db.session.delete(todo)
            db.session.commit()
            flash("Aufgabe erfolgreich gelöscht.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Löschen: {e}", "danger")
    return redirect(url_for('todo_bp.index'))

# NEUE FUNKTION: CSV-Export
@todo_bp.route('/export/csv')
@login_required
def export_csv():
    todos = ToDo.query.order_by(ToDo.start_date.asc()).all()
    
    # Erstelle eine In-Memory-Textdatei
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    # Schreibe die Kopfzeile
    writer.writerow(['ID', 'Beschreibung', 'Kategorie', 'Status', 'Startdatum', 'Enddatum', 
                     'Ersteller', 'Zugewiesen an', 'Bemerkungen'])
    
    # Schreibe die Datenzeilen
    for todo in todos:
        writer.writerow([
            todo.id,
            todo.description,
            todo.category.value if todo.category else '',
            todo.status.value if todo.status else '',
            todo.start_date.strftime('%Y-%m-%d %H:%M') if todo.start_date else '',
            todo.end_date.strftime('%Y-%m-%d') if todo.end_date else '',
            todo.creator.username if todo.creator else '',
            todo.assignee.username if todo.assignee else '',
            todo.notes
        ])
    
    # Bereite die Antwort vor
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=todo_export.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    
    return response