import os
from flask import Blueprint, render_template, jsonify, current_app, abort
from flask_login import login_required
from models import GCodeFile, Job
from gcode_parser import parse_gcode

visualizer_bp = Blueprint('visualizer_bp', __name__, url_prefix='/visualizer')

@visualizer_bp.route('/view/<int:gcode_file_id>')
@login_required
def view_gcode(gcode_file_id):
    """Zeigt die 3D-Visualisierungsseite für eine G-Code-Datei an."""
    gcode_file = GCodeFile.query.get_or_404(gcode_file_id)
    job = Job.query.filter_by(gcode_file_id=gcode_file.id).first()

    printer_name = "N/A"
    bed_size_x = 220  # Standardwert, falls kein Drucker zugewiesen
    bed_size_y = 220  # Standardwert, falls kein Drucker zugewiesen

    if job and job.assigned_printer:
        printer = job.assigned_printer
        printer_name = printer.name
        # Lade die tatsächlichen Druckbettmaße, falls in der DB vorhanden
        if printer.build_volume_w:
            bed_size_x = printer.build_volume_w
        # Annahme: In models.py ist build_volume_h die Tiefe (Y-Achse)
        if printer.build_volume_h:
            bed_size_y = printer.build_volume_h

    return render_template(
        'visualizer/viewer.html', 
        gcode_file=gcode_file, 
        printer_name=printer_name,
        bed_size_x=bed_size_x,
        bed_size_y=bed_size_y
    )

@visualizer_bp.route('/api/gcode_paths/<int:gcode_file_id>')
@login_required
def get_gcode_paths(gcode_file_id):
    """API-Endpunkt, der die geparsten G-Code-Pfade als JSON zurückgibt."""
    gcode_file = GCodeFile.query.get_or_404(gcode_file_id)
    
    file_path = os.path.join(current_app.config['GCODE_FOLDER'], gcode_file.filename)
    if not os.path.exists(file_path):
        abort(404, description="G-Code-Datei auf dem Server nicht gefunden.")

    paths = parse_gcode(file_path)
    
    return jsonify(paths)