from flask import Blueprint, render_template
from flask_login import login_required
from models import Printer # <-- WICHTIG: Printer-Modell importieren

# Erstellt den neuen Blueprint für unsere Seite
digital_twin_bp = Blueprint('digital_twin_bp', __name__, url_prefix='/digital_twin')

@digital_twin_bp.route('/')
@login_required
def index():
    """Rendert die Hauptseite für den Digitalen Zwilling."""
    
    # KORREKTUR: Lade alle Drucker aus der Datenbank
    printers = Printer.query.all()
    
    # Übergib die Drucker-Liste an das Template, damit es sie verwenden kann
    return render_template('digital_twin/index.html', printers=printers)