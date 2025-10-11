# validators.py
# Neue Datei im Hauptverzeichnis erstellen

import datetime
from collections import defaultdict, deque
from models import Job, JobDependency, JobStatus, DependencyType, DeadlineStatus
from extensions import db


class DependencyValidator:
    """Validiert Job-Abhängigkeiten und erkennt Zyklen"""
    
    @staticmethod
    def has_cycle(job_id, depends_on_id, db_session):
        """
        Prüft ob eine neue Abhängigkeit einen Zyklus erzeugen würde.
        Verwendet Tiefensuche (DFS) für Zyklenerkennung.
        
        Args:
            job_id: ID des abhängigen Jobs
            depends_on_id: ID des Jobs von dem abhängig gemacht werden soll
            db_session: SQLAlchemy Session
            
        Returns:
            bool: True wenn Zyklus existiert
        """
        # Verhindere Selbst-Abhängigkeiten
        if job_id == depends_on_id:
            return True
        
        visited = set()
        stack = [depends_on_id]
        
        while stack:
            current = stack.pop()
            
            if current == job_id:
                return True  # Zyklus gefunden!
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # Finde alle Jobs von denen current abhängt
            deps = db_session.query(JobDependency.depends_on_job_id)\
                .filter_by(job_id=current).all()
            
            for (dep_id,) in deps:
                stack.append(dep_id)
        
        return False
    
    @staticmethod
    def validate_dependency(job_id, depends_on_id, db_session):
        """
        Umfassende Validierung einer Abhängigkeit.
        
        Returns:
            tuple: (is_valid: bool, message: str)
        """
        # Prüfe ob Jobs existieren
        job = db_session.get(Job, job_id)
        depends_on = db_session.get(Job, depends_on_id)
        
        if not job or not depends_on:
            return False, "Ein oder beide Jobs existieren nicht"
        
        # Prüfe Selbst-Abhängigkeit
        if job_id == depends_on_id:
            return False, "Ein Job kann nicht von sich selbst abhängen"
        
        # Prüfe Zyklus
        if DependencyValidator.has_cycle(job_id, depends_on_id, db_session):
            return False, "Diese Abhängigkeit würde einen Zyklus erzeugen"
        
        # Prüfe ob Abhängigkeit bereits existiert
        existing = db_session.query(JobDependency).filter_by(
            job_id=job_id, 
            depends_on_job_id=depends_on_id
        ).first()
        
        if existing:
            return False, "Diese Abhängigkeit existiert bereits"
        
        # Prüfe ob umgekehrte Abhängigkeit existiert
        reverse = db_session.query(JobDependency).filter_by(
            job_id=depends_on_id,
            depends_on_job_id=job_id
        ).first()
        
        if reverse:
            return False, "Die umgekehrte Abhängigkeit existiert bereits"
        
        return True, "Validierung erfolgreich"
    
    @staticmethod
    def topological_sort(jobs):
        """
        Sortiert Jobs topologisch basierend auf Abhängigkeiten.
        Verwendet Kahn's Algorithmus.
        
        Args:
            jobs: Liste von Job-Objekten
            
        Returns:
            list: Sortierte Job-Liste oder None bei Zyklus
        """
        if not jobs:
            return []
        
        # Erstelle Adjazenzliste und In-Degree Map
        graph = defaultdict(list)
        in_degree = {job.id: 0 for job in jobs}
        job_map = {job.id: job for job in jobs}
        
        for job in jobs:
            for dep in job.dependencies:
                if dep.depends_on_job_id in in_degree:  # Nur wenn im aktuellen Set
                    graph[dep.depends_on_job_id].append(job.id)
                    in_degree[job.id] += 1
        
        # Kahn's Algorithmus
        queue = deque([job_id for job_id, degree in in_degree.items() if degree == 0])
        sorted_job_ids = []
        
        while queue:
            current = queue.popleft()
            sorted_job_ids.append(current)
            
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Zyklus-Check
        if len(sorted_job_ids) != len(jobs):
            return None  # Zyklus erkannt
        
        # Gib Jobs in sortierter Reihenfolge zurück
        return [job_map[job_id] for job_id in sorted_job_ids]
    
    @staticmethod
    def get_dependency_graph(jobs):
        """
        Erstellt einen Abhängigkeitsgraphen als Dictionary.
        Nützlich für Visualisierungen.
        
        Returns:
            dict: {job_id: [list_of_dependent_job_ids]}
        """
        graph = defaultdict(list)
        
        for job in jobs:
            for dep in job.dependencies:
                graph[dep.depends_on_job_id].append(job.id)
        
        return dict(graph)


class CriticalPathCalculator:
    """Berechnet den kritischen Pfad für ein Projekt (CPM - Critical Path Method)"""
    
    @staticmethod
    def calculate(project):
        """
        Berechnet kritischen Pfad eines Projekts.
        Markiert alle Jobs auf dem kritischen Pfad.
        
        Args:
            project: Project-Objekt
            
        Returns:
            list: Jobs auf dem kritischen Pfad
        """
        # Lade alle nicht-abgeschlossenen Jobs
        jobs = list(project.jobs.filter(
            Job.status.in_([JobStatus.PENDING, JobStatus.ASSIGNED, JobStatus.QUEUED, JobStatus.PRINTING])
        ))
        
        if not jobs:
            return []
        
        # Sortiere topologisch
        sorted_jobs = DependencyValidator.topological_sort(jobs)
        if not sorted_jobs:
            return []  # Zyklus erkannt
        
        # Erstelle Job-Maps für schnellen Zugriff
        job_map = {job.id: job for job in sorted_jobs}
        
        # Forward Pass: Earliest Start/Finish Times
        earliest_start = {}
        earliest_finish = {}
        
        for job in sorted_jobs:
            # Geschätzte Dauer in Minuten
            duration = 0
            if job.gcode_file and job.gcode_file.estimated_print_time_min:
                duration = job.gcode_file.estimated_print_time_min
            
            # Earliest Start ist max(Earliest Finish der Vorgänger)
            es = 0
            for dep in job.dependencies:
                if dep.dependency_type == DependencyType.FINISH_TO_START:
                    if dep.depends_on_job_id in earliest_finish:
                        es = max(es, earliest_finish[dep.depends_on_job_id])
            
            earliest_start[job.id] = es
            earliest_finish[job.id] = es + duration
        
        # Backward Pass: Latest Start/Finish Times
        latest_start = {}
        latest_finish = {}
        
        # Projekt-Ende ist max(Earliest Finish)
        project_end = max(earliest_finish.values()) if earliest_finish else 0
        
        for job in reversed(sorted_jobs):
            duration = 0
            if job.gcode_file and job.gcode_file.estimated_print_time_min:
                duration = job.gcode_file.estimated_print_time_min
            
            # Latest Finish ist min(Latest Start der Nachfolger)
            lf = project_end
            for dependent in job.dependents:
                if dependent.job_id in latest_start:
                    lf = min(lf, latest_start[dependent.job_id])
            
            latest_finish[job.id] = lf
            latest_start[job.id] = lf - duration
        
        # Identifiziere kritischen Pfad (Slack = 0)
        critical_jobs = []
        
        for job in sorted_jobs:
            slack = latest_start[job.id] - earliest_start[job.id]
            
            if abs(slack) < 0.1:  # Float-Vergleich mit Toleranz
                job.is_on_critical_path = True
                critical_jobs.append(job)
            else:
                job.is_on_critical_path = False
            
            # Setze geschätzte Start-/Endzeiten
            now = datetime.datetime.utcnow()
            job.estimated_start_time = now + datetime.timedelta(minutes=earliest_start[job.id])
            job.estimated_end_time = now + datetime.timedelta(minutes=earliest_finish[job.id])
        
        return critical_jobs
    
    @staticmethod
    def calculate_slack_time(job, project):
        """
        Berechnet Slack Time (Pufferzeit) für einen Job.
        
        Returns:
            float: Slack in Minuten
        """
        all_jobs = list(project.jobs.filter(Job.status != JobStatus.COMPLETED))
        sorted_jobs = DependencyValidator.topological_sort(all_jobs)
        
        if not sorted_jobs or job not in sorted_jobs:
            return 0.0
        
        # Vereinfachte Berechnung ohne vollständigen CPM
        duration = 0
        if job.gcode_file and job.gcode_file.estimated_print_time_min:
            duration = job.gcode_file.estimated_print_time_min
        
        # Berechne maximale Zeit bis Deadline
        if job.deadline:
            hours_until_deadline = (job.deadline - datetime.datetime.utcnow()).total_seconds() / 60
            slack = hours_until_deadline - duration
            return max(0, slack)
        
        return float('inf')  # Keine Deadline = unendliche Pufferzeit


class PriorityCalculator:
    """Berechnet intelligente Prioritäts-Scores für Jobs"""
    
    @staticmethod
    def calculate_priority_score(job):
        """
        Berechnet Priorität basierend auf mehreren Faktoren:
        - Deadline-Dringlichkeit (0-50 Punkte)
        - Manuelle Priorität (0-25 Punkte)
        - Kritischer Pfad (0-25 Punkte)
        - Projekt-Wichtigkeit (0-10 Punkte)
        
        Returns:
            float: Score zwischen 0-110
        """
        score = 0.0
        
        # 1. Deadline-Dringlichkeit (bis 50 Punkte)
        if job.deadline:
            now = datetime.datetime.utcnow()
            hours_remaining = (job.deadline - now).total_seconds() / 3600
            
            if hours_remaining < 0:
                score += 50  # Überfällig = höchste Priorität
            elif hours_remaining < 6:
                score += 48
            elif hours_remaining < 12:
                score += 46
            elif hours_remaining < 24:
                score += 42
            elif hours_remaining < 48:
                score += 35
            elif hours_remaining < 72:
                score += 28
            elif hours_remaining < 120:  # 5 Tage
                score += 20
            elif hours_remaining < 168:  # 7 Tage
                score += 12
            else:
                # Lineare Abnahme bis 30 Tage
                score += max(0, 10 - (hours_remaining - 168) / 168 * 10)
        
        # 2. Manuelle Priorität (0-25 Punkte)
        # Annahme: priority ist 1-10, normalisiert auf 0-25
        score += (job.priority / 10) * 25
        
        # 3. Kritischer Pfad (25 Punkte wenn True)
        if job.is_on_critical_path:
            score += 25
        
        # 4. Projekt-Wichtigkeit (0-10 Punkte)
        if job.project:
            if job.project.deadline:
                proj_hours_remaining = (
                    job.project.deadline - datetime.datetime.utcnow()
                ).total_seconds() / 3600
                
                if proj_hours_remaining < 24:
                    score += 10
                elif proj_hours_remaining < 48:
                    score += 8
                elif proj_hours_remaining < 72:
                    score += 6
                elif proj_hours_remaining < 120:
                    score += 4
                else:
                    score += 2
        
        # 5. Abhängigkeits-Dringlichkeit (bis 10 Punkte)
        # Jobs die andere blockieren bekommen Extra-Priorität
        blocking_count = len(job.dependents)
        score += min(10, blocking_count * 2)
        
        return round(score, 2)
    
    @staticmethod
    def calculate_all_priorities(project):
        """
        Berechnet Prioritäten für alle Jobs eines Projekts.
        Führt zuerst CPM aus, dann Prioritätsberechnung.
        """
        # Berechne kritischen Pfad
        CriticalPathCalculator.calculate(project)
        
        # Berechne Prioritäten
        for job in project.jobs:
            job.priority_score = PriorityCalculator.calculate_priority_score(job)
        
        db.session.commit()


class SchedulingOptimizer:
    """Optimiert Job-Zuweisung basierend auf verschiedenen Strategien"""
    
    @staticmethod
    def find_optimal_printer(job, available_printers, strategy='priority'):
        """
        Findet optimalen Drucker für einen Job.
        
        Args:
            job: Job-Objekt
            available_printers: Liste verfügbarer Drucker
            strategy: 'priority', 'fastest', 'balanced'
            
        Returns:
            Printer oder None
        """
        if not available_printers:
            return None
        
        suitable = []
        
        for printer in available_printers:
            # Prüfe Zeitfenster
            if not printer.is_available_at():
                continue
            
            # Prüfe Material-Kompatibilität
            if job.required_filament_type:
                loaded_spool = printer.assigned_spools.filter_by(is_in_use=True).first()
                if loaded_spool and loaded_spool.filament_type_id != job.required_filament_type.id:
                    continue
            
            suitable.append(printer)
        
        if not suitable:
            return None
        
        # Wähle basierend auf Strategie
        if strategy == 'priority':
            # Drucker mit niedrigster aktueller Auslastung
            return min(suitable, key=lambda p: p.jobs.filter(
                Job.status.in_([JobStatus.QUEUED, JobStatus.ASSIGNED])
            ).count())
        
        elif strategy == 'fastest':
            # Drucker mit kürzester Warteschlange (Zeit)
            def queue_time(p):
                queued = p.jobs.filter(Job.status.in_([JobStatus.QUEUED, JobStatus.ASSIGNED])).all()
                return sum(j.gcode_file.estimated_print_time_min or 0 for j in queued if j.gcode_file)
            
            return min(suitable, key=queue_time)
        
        else:  # balanced
            # Erste verfügbare
            return suitable[0]
    
    @staticmethod
    def calculate_job_urgency(job):
        """
        Berechnet Dringlichkeit eines Jobs (0-1).
        Kombiniert Deadline und Abhängigkeiten.
        """
        urgency = 0.0
        
        # Deadline-basierte Dringlichkeit
        if job.deadline:
            hours_left = (job.deadline - datetime.datetime.utcnow()).total_seconds() / 3600
            if hours_left < 0:
                urgency = 1.0
            else:
                # Exponential decay: dringlicher je näher Deadline
                urgency = max(0, 1 - (hours_left / 168))  # 7 Tage Normalisierung
        
        # Kritischer Pfad erhöht Dringlichkeit
        if job.is_on_critical_path:
            urgency = min(1.0, urgency + 0.3)
        
        # Blockierende Jobs sind dringlicher
        if job.dependents:
            urgency = min(1.0, urgency + 0.1 * len(job.dependents))
        
        return round(urgency, 3)