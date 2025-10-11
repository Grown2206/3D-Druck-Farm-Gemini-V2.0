# utils.py - NEUER DECORATOR für sichere DB-Operationen

import time
import logging
from functools import wraps
from sqlalchemy.exc import OperationalError, IntegrityError
from extensions import db

def safe_db_operation(max_retries=3, delay=0.1):
    """
    Decorator für sichere Datenbank-Operationen mit Retry-Logic.
    
    Args:
        max_retries: Maximale Anzahl Wiederholungsversuche
        delay: Wartezeit zwischen Versuchen in Sekunden
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    # Versuche die Operation
                    result = func(*args, **kwargs)
                    
                    # Bei Erfolg: Commit und return
                    if hasattr(db.session, 'commit'):
                        db.session.commit()
                    return result
                    
                except (OperationalError, IntegrityError) as e:
                    last_exception = e
                    
                    # Rollback bei Fehler
                    try:
                        db.session.rollback()
                    except:
                        pass
                    
                    if attempt < max_retries:
                        logging.warning(f"DB operation failed (attempt {attempt + 1}), retrying: {e}")
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    else:
                        logging.error(f"DB operation failed after {max_retries} retries: {e}")
                        break
                        
                except Exception as e:
                    # Für andere Fehler: kein Retry
                    try:
                        db.session.rollback()
                    except:
                        pass
                    raise e
            
            # Alle Versuche fehlgeschlagen
            raise last_exception if last_exception else Exception("DB operation failed")
            
        return wrapper
    return decorator


# Beispiel-Nutzung in routes/jobs.py
@safe_db_operation(max_retries=3)
def create_job_safely(job_data):
    """Sichere Job-Erstellung mit Retry-Logic."""
    job = Job(**job_data)
    db.session.add(job)
    # Commit wird automatisch vom Decorator gemacht
    return job


# Alternative: Context Manager für sichere Operationen
from contextlib import contextmanager

@contextmanager
def safe_db_session():
    """Context Manager für sichere DB-Sessions."""
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database operation failed: {e}")
        raise
    finally:
        db.session.close()


# Verwendung:
# with safe_db_session() as session:
#     job = Job(name="Test Job")
#     session.add(job)
#     # Automatischer Commit bei Erfolg, Rollback bei Fehler


# extensions.py - VERBESSERTE DB-KONFIGURATION für Concurrency
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

db = SQLAlchemy()

# SQLite-Optimierungen für bessere Concurrency
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Optimiert SQLite für bessere Concurrency."""
    if 'sqlite' in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        
        # WAL-Modus für bessere Concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        
        # Längere Timeouts für Lock-Konflikte
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 Sekunden
        
        # Foreign Key Constraints aktivieren
        cursor.execute("PRAGMA foreign_keys=ON")
        
        # Synchronous-Modus optimieren
        cursor.execute("PRAGMA synchronous=NORMAL")
        
        cursor.close()


# models.py - IMPROVED Job Model mit besserer ID-Behandlung
class Job(db.Model):
    # ... existing fields ...
    
    def save_safely(self):
        """Sichere Speicherung mit Retry-Logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                db.session.add(self)
                db.session.commit()
                return self
            except Exception as e:
                db.session.rollback()
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.1 * (2 ** attempt))
        
    @classmethod
    def create_safely(cls, **kwargs):
        """Sichere Job-Erstellung mit sofortiger ID-Vergabe."""
        job = cls(**kwargs)
        
        try:
            db.session.add(job)
            db.session.flush()  # ID vergeben ohne Commit
            job_id = job.id
            db.session.commit()
            return job
        except Exception as e:
            db.session.rollback()
            raise e