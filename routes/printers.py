# /routes/printers.py
import os
import uuid
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from extensions import db
from models import Printer, MaintenanceLog, PrinterStatus, APIType, CameraSource, BedType, PrinterType, MaintenanceTaskType
from flask_login import login_required, current_user
from .forms import MaintenanceLogForm, update_model_from_form
import datetime

printers_bp = Blueprint('printers_bp', __name__)

@printers_bp.route('/')
@login_required
def list_printers():
    printers = Printer.query.order_by(Printer.name).all()
    return render_template('printers/list.html', printers=printers)

@printers_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_printer():
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Ein Druckername ist erforderlich.', 'danger')
            return render_template('printers/add_edit.html', printer=None, form_title="Neuen Drucker hinzufügen")

        if Printer.query.filter_by(name=name).first():
            flash('Ein Drucker mit diesem Namen existiert bereits.', 'danger')
            form_data = request.form
            return render_template('printers/add_edit.html', printer=form_data, form_title="Neuen Drucker hinzufügen")

        new_printer = Printer(name=name)
        # Standard-Felder über Helper aktualisieren
        update_model_from_form(new_printer, request.form, get_printer_field_map())
        # Kalibrierungs-Einstellungen manuell verarbeiten
        process_calibration_form(new_printer, request.form)

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                file_path = os.path.join(current_app.config['PRINTER_IMAGES_FOLDER'], unique_filename)
                file.save(file_path)
                new_printer.image_url = f"uploads/printer_images/{unique_filename}"
            elif file.filename != '':
                flash('Ungültiger Bilddateityp.', 'warning')

        try:
            db.session.add(new_printer)
            db.session.commit()
            flash(f'Drucker "{name}" erfolgreich hinzugefügt.', 'success')
            return redirect(url_for('printers_bp.list_printers'))
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Hinzufügen des Druckers: {str(e)}', 'danger')

    return render_template('printers/add_edit.html', printer=None, form_title="Neuen Drucker hinzufügen")


@printers_bp.route('/edit/<int:printer_id>', methods=['GET', 'POST'])
@login_required
def edit_printer(printer_id):
    printer = db.session.get(Printer, printer_id)
    if not printer:
        flash('Drucker nicht gefunden.', 'danger')
        return redirect(url_for('printers_bp.list_printers'))

    if request.method == 'POST':
        new_name = request.form.get('name')
        if Printer.query.filter(Printer.id != printer_id, Printer.name == new_name).first():
            flash('Ein anderer Drucker mit diesem Namen existiert bereits.', 'danger')
            # printer-Objekt wieder an das Template übergeben, damit die alten Werte angezeigt werden
            return render_template('printers/add_edit.html', printer=printer, form_title="Drucker bearbeiten")

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                if printer.image_url:
                    old_image_path = os.path.join(current_app.config['STATIC_FOLDER'], printer.image_url)
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
                
                filename = secure_filename(file.filename)
                unique_filename = f"{printer.id}_{uuid.uuid4().hex[:8]}_{filename}"
                file_path = os.path.join(current_app.config['PRINTER_IMAGES_FOLDER'], unique_filename)
                file.save(file_path)
                printer.image_url = f"uploads/printer_images/{unique_filename}"
            elif file.filename != '':
                flash('Ungültiger Bilddateityp.', 'warning')

        # Standard-Felder über Helper aktualisieren
        update_model_from_form(printer, request.form, get_printer_field_map())
        # Kalibrierungs-Einstellungen manuell verarbeiten
        process_calibration_form(printer, request.form)

        try:
            db.session.commit()
            flash(f'Drucker "{printer.name}" erfolgreich aktualisiert.', 'success')
            return redirect(url_for('printers_bp.printer_details', printer_id=printer_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Aktualisieren des Druckers: {str(e)}', 'danger')

    return render_template('printers/add_edit.html', printer=printer, form_title="Drucker bearbeiten")


@printers_bp.route('/delete/<int:printer_id>', methods=['POST'])
@login_required
def delete_printer(printer_id):
    printer = db.session.get(Printer, printer_id)
    if printer:
        try:
            if printer.jobs.first():
                flash(f'Drucker "{printer.name}" kann nicht gelöscht werden, da ihm noch Jobs zugewiesen sind.', 'warning')
                return redirect(url_for('printers_bp.list_printers'))
            
            if printer.image_url:
                image_path = os.path.join(current_app.config['STATIC_FOLDER'], printer.image_url)
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            MaintenanceLog.query.filter_by(printer_id=printer.id).delete()

            db.session.delete(printer)
            db.session.commit()
            flash(f'Drucker "{printer.name}" wurde gelöscht.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Löschen des Druckers: {str(e)}', 'danger')
    else:
        flash('Drucker nicht gefunden.', 'danger')
    return redirect(url_for('printers_bp.list_printers'))

@printers_bp.route('/copy/<int:printer_id>', methods=['POST'])
@login_required
def copy_printer(printer_id):
    printer_to_copy = db.session.get(Printer, printer_id)
    if not printer_to_copy:
        flash("Drucker nicht gefunden.", "danger")
        return redirect(url_for('printers_bp.list_printers'))

    try:
        base_name = f"{printer_to_copy.name} (Kopie)"
        new_name = base_name
        counter = 1
        while Printer.query.filter_by(name=new_name).first():
            new_name = f"{base_name} {counter}"
            counter += 1

        new_printer = Printer(
            name=new_name,
            model=printer_to_copy.model,
            printer_type=printer_to_copy.printer_type,
            max_speed=printer_to_copy.max_speed,
            max_acceleration=printer_to_copy.max_acceleration,
            extruder_count=printer_to_copy.extruder_count,
            heated_chamber=printer_to_copy.heated_chamber,
            heated_chamber_temp=printer_to_copy.heated_chamber_temp,
            bed_type=printer_to_copy.bed_type,
            purchase_cost=printer_to_copy.purchase_cost,
            camera_source=printer_to_copy.camera_source,
            webcam_url=printer_to_copy.webcam_url,
            compatible_material_types=printer_to_copy.compatible_material_types,
            build_volume_l=printer_to_copy.build_volume_l,
            build_volume_w=printer_to_copy.build_volume_w,
            build_volume_h=printer_to_copy.build_volume_h,
            has_enclosure=printer_to_copy.has_enclosure,
            has_filter=printer_to_copy.has_filter,
            has_led=printer_to_copy.has_led,
            has_camera=printer_to_copy.has_camera,
            has_ace=printer_to_copy.has_ace,
            location=printer_to_copy.location,
            cost_per_hour=printer_to_copy.cost_per_hour,
            power_consumption_w=printer_to_copy.power_consumption_w,
            energy_price_kwh=printer_to_copy.energy_price_kwh,
            notes=printer_to_copy.notes,
            maintenance_interval_h=printer_to_copy.maintenance_interval_h
        )
        
        new_printer.status = PrinterStatus.IDLE
        new_printer.api_type = APIType.NONE
        
        db.session.add(new_printer)
        db.session.commit()
        flash(f"Drucker '{printer_to_copy.name}' wurde erfolgreich als '{new_name}' kopiert.", 'success')

    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Kopieren des Druckers: {e}", "danger")

    return redirect(url_for('printers_bp.list_printers'))


@printers_bp.route('/details/<int:printer_id>')
@login_required
def printer_details(printer_id):
    printer = db.session.get(Printer, printer_id)
    if not printer:
        flash('Drucker nicht gefunden.', 'danger')
        return redirect(url_for('printers_bp.list_printers'))
    
    maintenance_logs = MaintenanceLog.query.filter_by(printer_id=printer_id).order_by(MaintenanceLog.timestamp.desc()).all()
    
    return render_template('printers/details.html', printer=printer, maintenance_logs=maintenance_logs)

@printers_bp.route('/<int:printer_id>/add_maintenance', methods=['POST'])
@login_required
def add_maintenance_log(printer_id):
    printer = db.session.get(Printer, printer_id)
    if not printer:
        flash('Drucker nicht gefunden.', 'danger')
        return redirect(url_for('printers_bp.list_printers'))

    data = request.form
    notes = data.get('notes', '')
    
    checklist_items = {
        'check-belts': 'Riemenspannung geprüft',
        'check-screws': 'Schrauben geprüft',
        'check-lubrication': 'Geschmiert',
        'check-fans': 'Lüfter gereinigt',
        'check-ptfe': 'PTFE-Schlauch geprüft',
        'check-calibration': 'Kalibrierung durchgeführt',
        'check-nozzle': 'Düse gewechselt'
    }
    
    completed_tasks = []
    current_checklist_state = {}
    is_checklist_item_checked = False
    for key, description in checklist_items.items():
        is_checked = key in data
        current_checklist_state[key] = is_checked
        if is_checked:
            completed_tasks.append(description)
            is_checklist_item_checked = True

    full_notes = notes
    if completed_tasks:
        completed_str = "\n".join(f"- {task}" for task in completed_tasks)
        if notes.strip():
            full_notes = f"{notes.strip()}\n\nAbgeschlossene Checklisten-Punkte:\n{completed_str}"
        else:
            full_notes = f"Abgeschlossene Checklisten-Punkte:\n{completed_str}"
    
    if not full_notes.strip():
        flash("Es wurde kein Wartungspunkt ausgewählt oder eine Notiz hinzugefügt. Es wird kein Protokoll erstellt.", "info")
        return redirect(url_for('printers_bp.printer_details', printer_id=printer_id))
        
    task_type = MaintenanceTaskType.CHECKLIST if is_checklist_item_checked else MaintenanceTaskType.GENERAL

    new_log = MaintenanceLog(
        printer_id=printer_id,
        user_id=current_user.id,
        task_type=task_type,
        notes=full_notes.strip()
    )
    
    if 'check-belts' in data:
        printer.last_belt_tension_date = datetime.date.today()
    if 'check-nozzle' in data:
        printer.last_nozzle_change_h = printer.total_print_hours or 0
    
    general_maintenance_tasks = ['check-lubrication', 'check-calibration', 'check-screws', 'check-fans']
    if any(task in data for task in general_maintenance_tasks):
        printer.last_maintenance_date = datetime.date.today()
        printer.last_maintenance_h = printer.total_print_hours or 0

    printer.maintenance_checklist_state = current_checklist_state

    try:
        db.session.add(new_log)
        db.session.commit()
        flash('Wartungsprotokoll erfolgreich erstellt.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Hinzufügen des Protokolls: {str(e)}', 'danger')

    return redirect(url_for('printers_bp.printer_details', printer_id=printer_id))


@printers_bp.route('/connectivity/<int:printer_id>')
@login_required
def printer_connectivity(printer_id):
    printer = db.session.get(Printer, printer_id)
    if not printer:
        flash('Drucker nicht gefunden.', 'danger')
        return redirect(url_for('printers_bp.list_printers'))
    return render_template('printers/connectivity.html', printer=printer)


# --- Hilfsfunktionen ---
def allowed_file(filename):
    """Überprüft, ob eine Datei eine zulässige Bild-Endung hat."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_printer_field_map():
    """Gibt eine Zuordnung von Formularfeldern zu Modellattributen (ohne Kalibrierungseinstellungen) zurück."""
    return {
        'name': ('name', str), 'model': ('model', str), 'status': ('status', PrinterStatus),
        'printer_type': ('printer_type', PrinterType), 'max_speed': ('max_speed', int),
        'max_acceleration': ('max_acceleration', int), 'extruder_count': ('extruder_count', int),
        'heated_chamber': ('heated_chamber', bool), 'heated_chamber_temp': ('heated_chamber_temp', int),
        'bed_type': ('bed_type', BedType), 'purchase_cost': ('purchase_cost', float),
        'camera_source': ('camera_source', CameraSource), 'webcam_url': ('webcam_url', str),
        'compatible_material_types': ('compatible_material_types', str), 'build_volume_l': ('build_volume_l', float),
        'build_volume_w': ('build_volume_w', float), 'build_volume_h': ('build_volume_h', float),
        'max_nozzle_temp': ('max_nozzle_temp', int), 'max_bed_temp': ('max_bed_temp', int),
        'location': ('location', str), 'cost_per_hour': ('cost_per_hour', float),
        'power_consumption_w': ('power_consumption_w', int), 'energy_price_kwh': ('energy_price_kwh', float),
        'notes': ('notes', str), 'ip_address': ('ip_address', str), 'api_key': ('api_key', str),
        'api_type': ('api_type', APIType), 'maintenance_interval_h': ('maintenance_interval_h', int),
        # ##### HIER IST DIE KORREKTUR: Nur die historischen Basiswerte sind direkt editierbar #####
        'historical_print_hours': ('historical_print_hours', float),
        'historical_filament_used_g': ('historical_filament_used_g', float),
        'historical_jobs_count': ('historical_jobs_count', int),
        'useful_life_years': ('useful_life_years', int),
        'salvage_value': ('salvage_value', float),
        'annual_maintenance_cost': ('annual_maintenance_cost', float),
        'annual_operating_hours': ('annual_operating_hours', int),
        'imputed_interest_rate': ('imputed_interest_rate', float),
        'commissioning_date': ('commissioning_date', lambda d: datetime.datetime.strptime(d, '%Y-%m-%d').date() if d else None),
        'has_enclosure': ('has_enclosure', bool), 'has_filter': ('has_filter', bool),
        'has_camera': ('has_camera', bool), 'has_led': ('has_led', bool), 'has_ace': ('has_ace', bool),
        # Kalibrierungs-Ergebnisse
        'z_offset': ('z_offset', float),
        'last_vibration_calibration_date': ('last_vibration_calibration_date', lambda d: datetime.datetime.strptime(d, '%Y-%m-%d').date() if d else None),
        'flow_rate_result': ('flow_rate_result', float),
        'pressure_advance_result': ('pressure_advance_result', float),
        'max_volumetric_speed_result': ('max_volumetric_speed_result', float),
        'vfa_optimal_speed': ('vfa_optimal_speed', int),
    }

def process_calibration_form(printer, form):
    """Liest Kalibrierungs-Einstellungen aus dem Formular und speichert sie als JSON im Drucker-Objekt."""
    
    def get_form_value(key, value_type=str):
        val = form.get(key)
        if val is None or val == '':
            return None
        try:
            return value_type(val)
        except (ValueError, TypeError):
            return None

    # Flow Rate / Max Volumetric Speed Test
    printer.flow_rate_settings = {
        'start': get_form_value('fr_start', int),
        'end': get_form_value('fr_end', int),
        'step': get_form_value('fr_step', float)
    }

    # Pressure Advance Test
    printer.pressure_advance_settings = {
        'method': get_form_value('pa_method'),
        'start': get_form_value('pa_start', float),
        'end': get_form_value('pa_end', float),
        'step': get_form_value('pa_step', float)
    }

    # VFA Test
    printer.vfa_test_settings = {
        'start_speed': get_form_value('vfa_start_speed', int),
        'end_speed': get_form_value('vfa_end_speed', int),
        'step': get_form_value('vfa_step', int)
    }