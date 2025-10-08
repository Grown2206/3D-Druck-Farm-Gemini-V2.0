import click
from flask.cli import with_appcontext
from extensions import db
from models import (
    User, Printer, Job, FilamentType, FilamentSpool, 
    UserRole, PrinterStatus, JobStatus
)

@click.command('run-tests')
@with_appcontext
def test_suite_command():
    """Führt eine einfache Test-Suite aus, um die grundlegende Funktionalität zu prüfen."""
    click.echo("--- Starte Test-Suite ---")

    try:
        # --- Datenbank leeren ---
        click.echo("1. Leere Datenbank...")
        db.session.query(Job).delete()
        db.session.query(FilamentSpool).delete()
        db.session.query(FilamentType).delete()
        db.session.query(Printer).delete()
        db.session.query(User).delete()
        db.session.commit()
        click.echo("   ...erfolgreich.")

        # --- Testdaten erstellen ---
        click.echo("2. Erstelle Testdaten...")
        # Benutzer
        admin = User(username='test_admin', role=UserRole.ADMIN)
        admin.set_password('password')
        op = User(username='test_operator', role=UserRole.OPERATOR)
        op.set_password('password')
        db.session.add_all([admin, op])
        
        # Drucker
        p1 = Printer(name='Test Printer 1', model='Modell A', status=PrinterStatus.IDLE)
        p2 = Printer(name='Test Printer 2', model='Modell B', status=PrinterStatus.MAINTENANCE)
        db.session.add_all([p1, p2])

        # Filament
        ftype1 = FilamentType(manufacturer="TestCorp", name="Test PLA", material_type="PLA", color_hex="#FF0000")
        db.session.add(ftype1)
        db.session.flush() # ID für die Spule holen

        spool1 = FilamentSpool(filament_type_id=ftype1.id, initial_weight_g=1000, current_weight_g=800)
        db.session.add(spool1)

        # Jobs
        job1 = Job(name='Test Job 1', status=JobStatus.PENDING, priority=10)
        job2 = Job(name='Test Job 2', status=JobStatus.ASSIGNED, printer_id=p1.id, required_filament_type_id=ftype1.id)
        db.session.add_all([job1, job2])

        db.session.commit()
        click.echo("   ...erfolgreich.")

        # --- Überprüfungen ---
        click.echo("3. Führe Überprüfungen durch...")
        assert User.query.count() == 2, "Fehler: Benutzeranzahl stimmt nicht."
        assert Printer.query.count() == 2, "Fehler: Druckeranzahl stimmt nicht."
        assert FilamentType.query.count() == 1, "Fehler: Filament-Typ-Anzahl stimmt nicht."
        assert FilamentSpool.query.count() == 1, "Fehler: Spulenanzahl stimmt nicht."
        assert Job.query.count() == 2, "Fehler: Jobanzahl stimmt nicht."
        click.echo("   ...alle Überprüfungen erfolgreich.")

        click.secho("--- Test-Suite erfolgreich abgeschlossen ---", fg="green")

    except Exception as e:
        db.session.rollback()
        click.secho(f"--- FEHLER in der Test-Suite: {e} ---", fg="red")
    finally:
        # Datenbank nach Test wieder aufräumen
        db.session.query(Job).delete()
        db.session.query(FilamentSpool).delete()
        db.session.query(FilamentType).delete()
        db.session.query(Printer).delete()
        db.session.query(User).delete()
        db.session.commit()