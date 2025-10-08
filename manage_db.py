# manage_db.py
import click
import json
from flask.cli import with_appcontext
from extensions import db
# HIER DIE ANPASSUNG: FilamentType und FilamentSpool importieren
from models import User, Printer, FilamentType, FilamentSpool, Consumable

@click.command('export-data')
@with_appcontext
def export_data_command():
    """Exportiert alle relevanten Daten als JSON."""
    data = {
        'users': [user.__dict__ for user in User.query.all()],
        'printers': [printer.__dict__ for printer in Printer.query.all()],
        # HIER DIE ANPASSUNG: Neue Modelle exportieren
        'filament_types': [ftype.__dict__ for ftype in FilamentType.query.all()],
        'filament_spools': [spool.__dict__ for spool in FilamentSpool.query.all()],
        'consumables': [c.__dict__ for c in Consumable.query.all()]
    }
    # Interne SQLAlchemy-Status entfernen
    for table in data.values():
        for record in table:
            record.pop('_sa_instance_state', None)

    with open('db_export.json', 'w') as f:
        json.dump(data, f, indent=4, default=str)
    
    click.echo("Daten erfolgreich nach db_export.json exportiert.")

@click.command('import-data')
@click.argument('filepath')
@with_appcontext
def import_data_command(filepath):
    """Importiert Daten aus einer JSON-Datei."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # HINWEIS: Sehr einfache Import-Logik. Ersetzt alles.
        # Zuerst alles löschen (in umgekehrter Reihenfolge der Abhängigkeiten)
        db.session.query(Consumable).delete()
        # HIER DIE ANPASSUNG: Neue Modelle löschen
        db.session.query(FilamentSpool).delete()
        db.session.query(FilamentType).delete()
        db.session.query(Printer).delete()
        db.session.query(User).delete()
        
        for user_data in data.get('users', []):
            db.session.add(User(**user_data))
        for printer_data in data.get('printers', []):
            db.session.add(Printer(**printer_data))
        # HIER DIE ANPASSUNG: Neue Modelle importieren
        for ftype_data in data.get('filament_types', []):
            db.session.add(FilamentType(**ftype_data))
        for spool_data in data.get('filament_spools', []):
            db.session.add(FilamentSpool(**spool_data))
        for consumable_data in data.get('consumables', []):
            db.session.add(Consumable(**consumable_data))
            
        db.session.commit()
        click.echo(f"Daten erfolgreich aus {filepath} importiert.")

    except Exception as e:
        db.session.rollback()
        click.echo(f"Fehler beim Importieren: {e}")