# /routes/batch_planner.py
from flask import Blueprint, render_template
from flask_login import login_required
from models import Printer, FilamentType

# Blueprint für den neuen Batch-Planer erstellen
batch_planner_bp = Blueprint('batch_planner_bp', __name__, url_prefix='/batch-planner')

@batch_planner_bp.route('/')
@login_required
def index():
    """
    Zeigt die Hauptseite für die Batch-Planung an und lädt die notwendigen
    Auswahldaten für Drucker und Materialien.
    """
    # Lade alle Drucker und Filament-Typen aus der Datenbank
    printers = Printer.query.order_by(Printer.name).all()
    filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    
    return render_template('jobs/batch_planner.html', 
                           printers=printers, 
                           filament_types=filament_types)