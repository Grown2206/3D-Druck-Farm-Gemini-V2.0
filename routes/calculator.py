# /routes/calculator.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
# HIER DIE ANPASSUNG: Material durch FilamentType ersetzen
from models import CostCalculation, GCodeFile, FilamentType, Printer
from flask_login import login_required
import datetime # Import für Datum hinzugefügt

calculator_bp = Blueprint('calculator_bp', __name__, url_prefix='/calculator')

@calculator_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        return calculate()

    gcode_files = GCodeFile.query.order_by(GCodeFile.filename).all()
    # HIER DIE ANPASSUNG: Lade FilamentType statt Material
    filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    printers = Printer.query.order_by(Printer.name).all()
    
    return render_template('calculator/index.html', 
                           gcode_files=gcode_files, 
                           materials=filament_types, # Variable im Template heißt weiterhin materials der Einfachheit halber
                           printers=printers)

def calculate():
    """Führt die Kostenkalkulation durch und speichert das Ergebnis."""
    try:
        # Formulardaten sammeln
        gcode_file_id = request.form.get('gcode_file_id', type=int)
        # HIER DIE ANPASSUNG: ID von FilamentType holen
        filament_type_id = request.form.get('material_id', type=int)
        printer_id = request.form.get('printer_id', type=int)
        
        gcode = db.session.get(GCodeFile, gcode_file_id)
        # HIER DIE ANPASSUNG: FilamentType-Objekt holen
        filament_type = db.session.get(FilamentType, filament_type_id)
        printer = db.session.get(Printer, printer_id)

        if not all([gcode, filament_type, printer]):
            flash("Bitte G-Code, Material und Drucker auswählen.", "warning")
            return redirect(url_for('calculator_bp.index'))

        prep_time = request.form.get('preparation_time_min', 0, type=int)
        post_time = request.form.get('post_processing_time_min', 0, type=int)
        hourly_rate = request.form.get('employee_hourly_rate', 0, type=float)
        margin = request.form.get('margin_percent', 0, type=float)

        # Kosten berechnen
        # HIER DIE ANPASSUNG: Kosten pro Gramm aus FilamentType berechnen
        material_cost_per_g = (filament_type.cost_per_spool or 0) / (filament_type.spool_weight_g or 1000)
        material_cost = (gcode.material_needed_g or 0) * material_cost_per_g

        machine_cost_per_h = printer.calculated_cost_per_hour or printer.cost_per_hour or 0
        machine_cost = (gcode.estimated_print_time_min or 0) / 60 * machine_cost_per_h
        
        personnel_cost = (prep_time + post_time) / 60 * hourly_rate
        
        total_cost_without_margin = material_cost + machine_cost + personnel_cost
        total_price = total_cost_without_margin * (1 + (margin / 100))
        
        # Ergebnis in der DB speichern
        name = f"Kalkulation für {gcode.filename} am {datetime.datetime.now().strftime('%d.%m.%Y')}"
        new_calculation = CostCalculation(
            name=name,
            gcode_file_id=gcode.id,
            # HIER DIE ANPASSUNG: ID von FilamentType speichern
            filament_type_id=filament_type.id,
            printer_id=printer.id,
            preparation_time_min=prep_time,
            post_processing_time_min=post_time,
            employee_hourly_rate=hourly_rate,
            margin_percent=margin,
            material_cost=material_cost,
            machine_cost=machine_cost,
            personnel_cost=personnel_cost,
            total_cost_without_margin=total_cost_without_margin,
            total_price=total_price
        )
        db.session.add(new_calculation)
        db.session.commit()
        
        flash("Kalkulation erfolgreich erstellt.", "success")
        return redirect(url_for('calculator_bp.view', calc_id=new_calculation.id))

    except Exception as e:
        db.session.rollback()
        flash(f"Fehler bei der Kalkulation: {e}", "danger")
        return redirect(url_for('calculator_bp.index'))


@calculator_bp.route('/view/<int:calc_id>')
@login_required
def view(calc_id):
    calculation = db.session.get(CostCalculation, calc_id)
    if not calculation:
        flash("Kalkulation nicht gefunden.", "danger")
        return redirect(url_for('calculator_bp.index'))
    return render_template('calculator/view.html', calculation=calculation)