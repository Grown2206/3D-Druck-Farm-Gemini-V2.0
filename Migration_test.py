from app import create_app
from extensions import db
from models import Project, JobDependency, TimeWindow, Job

app = create_app()
with app.app_context():
    # Prüfe neue Tabellen
    print("Project count:", Project.query.count())
    print("JobDependency count:", JobDependency.query.count())
    print("TimeWindow count:", TimeWindow.query.count())
    
    # Prüfe neue Job-Spalten
    job = Job.query.first()
    if job:
        print("Job has deadline field:", hasattr(job, 'deadline'))
        print("Job has project_id field:", hasattr(job, 'project_id'))
        print("Job has priority_score field:", hasattr(job, 'priority_score'))