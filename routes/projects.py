# routes/projects.py
# Neue Datei im routes/ Ordner erstellen

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from extensions import db
from models import Project, Job, JobStatus, DeadlineStatus
from validators import CriticalPathCalculator, PriorityCalculator
import datetime

projects_bp = Blueprint('projects_bp', __name__, url_prefix='/projects')


@projects_bp.route('/')
@login_required
def list_projects():
    """Projekt-Übersicht mit Status-Informationen"""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    
    # Statistiken
    stats = {
        'total': len(projects),
        'active': len([p for p in projects if p.status == 'active']),
        'completed': len([p for p in projects if p.status == 'completed']),
        'at_risk': len([p for p in projects if p.deadline_status in [DeadlineStatus.RED, DeadlineStatus.OVERDUE]])
    }
    
    return render_template('projects/list.html', projects=projects, stats=stats)


@projects_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_project():
    """Neues Projekt erstellen"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            deadline_str = request.form.get('deadline')
            color = request.form.get('color', '#0d6efd')
            
            # Validierung
            if not name:
                flash('Projektname ist erforderlich', 'danger')
                return redirect(url_for('projects_bp.create_project'))
            
            # Prüfe ob Name bereits existiert
            existing = Project.query.filter_by(name=name).first()
            if existing:
                flash(f'Projekt mit dem Namen "{name}" existiert bereits', 'warning')
                return redirect(url_for('projects_bp.create_project'))
            
            # Deadline parsen
            deadline = None
            if deadline_str:
                try:
                    deadline = datetime.datetime.fromisoformat(deadline_str)
                except ValueError:
                    flash('Ungültiges Deadline-Format', 'warning')
            
            # Projekt erstellen
            project = Project(
                name=name,
                description=description if description else None,
                deadline=deadline,
                color=color,
                status='active'
            )
            
            db.session.add(project)
            db.session.commit()
            
            flash(f"✓ Projekt '{name}' erfolgreich erstellt", 'success')
            return redirect(url_for('projects_bp.view_project', project_id=project.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Erstellen: {e}', 'danger')
            return redirect(url_for('projects_bp.create_project'))
    
    return render_template('projects/create.html')


@projects_bp.route('/<int:project_id>')
@login_required
def view_project(project_id):
    """Projekt-Details mit Gantt-Chart und Job-Liste"""
    project = db.session.get(Project, project_id)
    
    if not project:
        flash('Projekt nicht gefunden', 'danger')
        return redirect(url_for('projects_bp.list_projects'))
    
    # Berechne kritischen Pfad
    critical_jobs = []
    try:
        critical_jobs = CriticalPathCalculator.calculate(project)
    except Exception as e:
        flash(f'Fehler bei Berechnung des kritischen Pfads: {e}', 'warning')
    
    # Lade Jobs
    jobs = project.jobs.order_by(Job.priority_score.desc(), Job.created_at).all()
    
    # Statistiken
    stats = {
        'total_jobs': len(jobs),
        'completed': len([j for j in jobs if j.status == JobStatus.COMPLETED]),
        'in_progress': len([j for j in jobs if j.status in [JobStatus.PRINTING, JobStatus.QUEUED, JobStatus.ASSIGNED]]),
        'pending': len([j for j in jobs if j.status == JobStatus.PENDING]),
        'critical_path_jobs': len(critical_jobs),
        'overdue_jobs': len([j for j in jobs if j.deadline_status == DeadlineStatus.OVERDUE])
    }
    
    return render_template('projects/view.html', 
                          project=project, 
                          jobs=jobs,
                          critical_jobs=critical_jobs,
                          stats=stats)


@projects_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    """Projekt bearbeiten"""
    project = db.session.get(Project, project_id)
    
    if not project:
        flash('Projekt nicht gefunden', 'danger')
        return redirect(url_for('projects_bp.list_projects'))
    
    if request.method == 'POST':
        try:
            project.name = request.form.get('name', project.name)
            project.description = request.form.get('description', project.description)
            project.color = request.form.get('color', project.color)
            project.status = request.form.get('status', project.status)
            
            deadline_str = request.form.get('deadline')
            if deadline_str:
                project.deadline = datetime.datetime.fromisoformat(deadline_str)
            else:
                project.deadline = None
            
            db.session.commit()
            flash('Projekt erfolgreich aktualisiert', 'success')
            return redirect(url_for('projects_bp.view_project', project_id=project.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Speichern: {e}', 'danger')
    
    return render_template('projects/edit.html', project=project)


@projects_bp.route('/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    """Projekt löschen"""
    project = db.session.get(Project, project_id)
    
    if not project:
        return jsonify({'error': 'Projekt nicht gefunden'}), 404
    
    try:
        # Prüfe ob noch Jobs existieren
        job_count = project.jobs.count()
        if job_count > 0:
            return jsonify({
                'error': f'Projekt hat noch {job_count} Jobs. Bitte erst Jobs entfernen.'
            }), 400
        
        name = project.name
        db.session.delete(project)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Projekt "{name}" gelöscht'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@projects_bp.route('/<int:project_id>/gantt')
@login_required
def project_gantt(project_id):
    """Gantt-Daten für Projekt mit kritischem Pfad (JSON für ApexCharts)"""
    project = db.session.get(Project, project_id)
    
    if not project:
        return jsonify({'error': 'Projekt nicht gefunden'}), 404
    
    try:
        # Berechne kritischen Pfad
        CriticalPathCalculator.calculate(project)
        
        # Lade relevante Jobs
        jobs = project.jobs.filter(
            Job.status.in_([
                JobStatus.PENDING, JobStatus.ASSIGNED, 
                JobStatus.QUEUED, JobStatus.PRINTING, JobStatus.COMPLETED
            ])
        ).order_by(Job.estimated_start_time).all()
        
        series_data = []
        now = datetime.datetime.utcnow()
        
        for job in jobs:
            # Bestimme Start/End-Zeit
            if job.status == JobStatus.COMPLETED:
                start = job.start_time or job.created_at
                end = job.end_time or job.completed_at or start
            else:
                start = job.estimated_start_time or now
                end = job.estimated_end_time or (start + datetime.timedelta(hours=1))
            
            # Farbe basierend auf Status und Priorität
            if job.is_on_critical_path:
                color = '#dc3545'  # Rot für kritischen Pfad
            elif job.deadline_status == DeadlineStatus.RED:
                color = '#ff6384'  # Rosa für dringende Deadline
            elif job.deadline_status == DeadlineStatus.OVERDUE:
                color = '#8b0000'  # Dunkelrot für überfällig
            elif job.status == JobStatus.PRINTING:
                color = '#198754'  # Grün für laufend
            elif job.status == JobStatus.COMPLETED:
                color = '#6c757d'  # Grau für abgeschlossen
            else:
                color = '#0d6efd'  # Blau für geplant
            
            series_data.append({
                'x': job.name[:30],  # Kürze Namen für bessere Darstellung
                'y': [
                    int(start.timestamp() * 1000),
                    int(end.timestamp() * 1000)
                ],
                'fillColor': color,
                'is_critical': job.is_on_critical_path,
                'deadline_status': job.deadline_status.value if job.deadline_status else None,
                'status': job.status.value,
                'priority_score': job.priority_score,
                'job_id': job.id
            })
        
        return jsonify([{
            'name': project.name,
            'data': series_data
        }])
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@projects_bp.route('/<int:project_id>/recalculate', methods=['POST'])
@login_required
def recalculate_project(project_id):
    """Kritischen Pfad und Prioritäten neu berechnen"""
    project = db.session.get(Project, project_id)
    
    if not project:
        return jsonify({'error': 'Projekt nicht gefunden'}), 404
    
    try:
        # Berechne kritischen Pfad
        critical_jobs = CriticalPathCalculator.calculate(project)
        
        # Berechne Prioritäten
        for job in project.jobs:
            job.priority_score = PriorityCalculator.calculate_priority_score(job)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'critical_jobs_count': len(critical_jobs),
            'message': 'Berechnung erfolgreich'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@projects_bp.route('/<int:project_id>/stats')
@login_required
def project_stats(project_id):
    """Detaillierte Projekt-Statistiken (JSON)"""
    project = db.session.get(Project, project_id)
    
    if not project:
        return jsonify({'error': 'Projekt nicht gefunden'}), 404
    
    jobs = project.jobs.all()
    
    # Berechne Statistiken
    total_time = sum(
        (j.gcode_file.estimated_print_time_min or 0) for j in jobs if j.gcode_file
    )
    
    completed_time = sum(
        (j.actual_print_duration_s or 0) / 60 for j in jobs if j.status == JobStatus.COMPLETED
    )
    
    stats = {
        'project_name': project.name,
        'completion_percentage': project.completion_percentage,
        'total_jobs': len(jobs),
        'completed_jobs': len([j for j in jobs if j.status == JobStatus.COMPLETED]),
        'total_estimated_time_hours': round(total_time / 60, 1),
        'completed_time_hours': round(completed_time / 60, 1),
        'deadline': project.deadline.isoformat() if project.deadline else None,
        'deadline_status': project.deadline_status.value if project.deadline_status else None,
        'estimated_completion': project.estimated_completion_time.isoformat(),
        'critical_path_length': len([j for j in jobs if j.is_on_critical_path]),
        'overdue_jobs': len([j for j in jobs if j.deadline_status == DeadlineStatus.OVERDUE]),
        'material_usage': {}  # Kann erweitert werden
    }
    
    return jsonify(stats)