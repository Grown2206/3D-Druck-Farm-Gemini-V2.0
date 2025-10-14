# tests/test_dependencies.py
import pytest
from models import Job, JobDependency, DependencyType
from validators import DependencyValidator

class TestDependencies:
    """Test-Suite für Job-Abhängigkeiten"""
    
    def test_no_self_dependency(self, db_session):
        """Test: Ein Job kann nicht von sich selbst abhängen"""
        job = Job(name="Test Job")
        db_session.add(job)
        db_session.commit()
        
        is_valid, message = DependencyValidator.validate_dependency(
            job.id, job.id, db_session
        )
        
        assert not is_valid
        assert "selbst abhängen" in message.lower()
    
    def test_no_circular_dependency(self, db_session):
        """Test: Zirkuläre Abhängigkeiten werden erkannt"""
        # Erstelle Jobs: A -> B -> C
        job_a = Job(name="Job A")
        job_b = Job(name="Job B")
        job_c = Job(name="Job C")
        
        db_session.add_all([job_a, job_b, job_c])
        db_session.commit()
        
        # A hängt von B ab
        dep1 = JobDependency(
            job_id=job_a.id, 
            depends_on_job_id=job_b.id,
            dependency_type=DependencyType.FINISH_TO_START
        )
        # B hängt von C ab
        dep2 = JobDependency(
            job_id=job_b.id,
            depends_on_job_id=job_c.id,
            dependency_type=DependencyType.FINISH_TO_START
        )
        
        db_session.add_all([dep1, dep2])
        db_session.commit()
        
        # Versuche C von A abhängig zu machen (würde Zyklus erzeugen)
        is_valid, message = DependencyValidator.validate_dependency(
            job_c.id, job_a.id, db_session
        )
        
        assert not is_valid
        assert "zyklus" in message.lower()
    
    def test_duplicate_dependency(self, db_session):
        """Test: Doppelte Abhängigkeiten werden verhindert"""
        job_a = Job(name="Job A")
        job_b = Job(name="Job B")
        
        db_session.add_all([job_a, job_b])
        db_session.commit()
        
        # Erste Abhängigkeit
        dep = JobDependency(
            job_id=job_a.id,
            depends_on_job_id=job_b.id,
            dependency_type=DependencyType.FINISH_TO_START
        )
        db_session.add(dep)
        db_session.commit()
        
        # Versuche gleiche Abhängigkeit nochmal
        is_valid, message = DependencyValidator.validate_dependency(
            job_a.id, job_b.id, db_session
        )
        
        assert not is_valid
        assert "existiert bereits" in message.lower()
    
    def test_can_start_with_dependencies(self, db_session):
        """Test: Job.can_start berücksichtigt Abhängigkeiten"""
        job_a = Job(name="Job A", status=JobStatus.PENDING)
        job_b = Job(name="Job B", status=JobStatus.PENDING)
        
        db_session.add_all([job_a, job_b])
        db_session.commit()
        
        # A hängt von B ab
        dep = JobDependency(
            job_id=job_a.id,
            depends_on_job_id=job_b.id,
            dependency_type=DependencyType.FINISH_TO_START
        )
        db_session.add(dep)
        db_session.commit()
        
        # A kann nicht starten, da B noch nicht abgeschlossen
        assert not job_a.can_start
        
        # B auf COMPLETED setzen
        job_b.status = JobStatus.COMPLETED
        db_session.commit()
        
        # Jetzt kann A starten
        assert job_a.can_start
    
    def test_api_add_dependency(self, client, auth_headers):
        """Test: API-Endpunkt zum Hinzufügen von Abhängigkeiten"""
        # Erstelle Test-Jobs
        response = client.post('/jobs/create', data={
            'name': 'Job A',
            'priority': 5
        }, headers=auth_headers)
        job_a_id = 1  # Annahme
        
        response = client.post('/jobs/create', data={
            'name': 'Job B',
            'priority': 5
        }, headers=auth_headers)
        job_b_id = 2  # Annahme
        
        # Füge Abhängigkeit hinzu
        response = client.post('/jobs/dependencies/add', 
            json={
                'job_id': job_a_id,
                'depends_on_id': job_b_id,
                'type': 'finish_to_start'
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'dependency' in data
    
    def test_api_remove_dependency(self, client, auth_headers, db_session):
        """Test: API-Endpunkt zum Entfernen von Abhängigkeiten"""
        # Setup: Erstelle Jobs und Abhängigkeit
        job_a = Job(name="Job A")
        job_b = Job(name="Job B")
        db_session.add_all([job_a, job_b])
        db_session.commit()
        
        dep = JobDependency(
            job_id=job_a.id,
            depends_on_job_id=job_b.id,
            dependency_type=DependencyType.FINISH_TO_START
        )
        db_session.add(dep)
        db_session.commit()
        
        # Entferne Abhängigkeit
        response = client.delete(
            f'/jobs/dependencies/remove/{dep.id}',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        
        # Verifiziere dass Abhängigkeit entfernt wurde
        assert JobDependency.query.get(dep.id) is None