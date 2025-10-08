# /routes/materials.py
# (imports am Anfang der Datei beibehalten)
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from extensions import db
from models import FilamentType, FilamentSpool, Printer
from flask_login import login_required
import datetime
from sqlalchemy.exc import IntegrityError
import qrcode
import base64
from io import BytesIO
import json # Import für QR-Code hinzugefügt
import io # Import für QR-Code hinzugefügt


materials_bp = Blueprint('materials_bp', __name__, url_prefix='/materials')

# --- FilamentType Routes (Obergruppe) ---

@materials_bp.route('/')
@login_required
def list_filaments():
    spools = FilamentSpool.query.join(FilamentType).order_by(FilamentType.manufacturer, FilamentType.name).all()
    printers = Printer.query.order_by(Printer.name).all()
    filament_types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    return render_template('materials/list.html', spools=spools, printers=printers, filament_types=filament_types)

@materials_bp.route('/types')
@login_required
def list_types():
    types = FilamentType.query.order_by(FilamentType.manufacturer, FilamentType.name).all()
    return render_template('materials/list_types.html', types=types)


@materials_bp.route('/types/add', methods=['GET', 'POST'])
@login_required
def add_type():
    if request.method == 'POST':
        try:
            new_type = FilamentType()
            update_type_from_form(new_type, request.form)
            db.session.add(new_type)
            db.session.commit()
            flash('Filament-Typ erfolgreich erstellt.', 'success')
            return redirect(url_for('materials_bp.list_types'))
        except IntegrityError:
            db.session.rollback()
            flash('Fehler: Ein Filament-Typ mit diesem Hersteller und Namen existiert bereits.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ein unerwarteter Fehler ist aufgetreten: {e}', 'danger')
    
    return render_template('materials/add_edit_type.html', type=None)


@materials_bp.route('/types/edit/<int:type_id>', methods=['GET', 'POST'])
@login_required
def edit_type(type_id):
    ftype = db.session.get(FilamentType, type_id)
    if not ftype:
        flash('Filament-Typ nicht gefunden.', 'danger')
        return redirect(url_for('materials_bp.list_types'))

    if request.method == 'POST':
        try:
            update_type_from_form(ftype, request.form)
            db.session.commit()
            flash('Filament-Typ erfolgreich aktualisiert.', 'success')
            return redirect(url_for('materials_bp.list_types'))
        except IntegrityError:
            db.session.rollback()
            flash('Fehler: Ein anderer Filament-Typ mit diesem Hersteller und Namen existiert bereits.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Ein unerwarteter Fehler ist aufgetreten: {e}', 'danger')
            
    return render_template('materials/add_edit_type.html', type=ftype)


@materials_bp.route('/types/delete/<int:type_id>', methods=['POST'])
@login_required
def delete_type(type_id):
    ftype = db.session.get(FilamentType, type_id)
    if ftype:
        if ftype.spools.count() > 0:
            flash('Kann nicht gelöscht werden: Es sind noch Spulen dieses Typs im Inventar.', 'warning')
        else:
            try:
                db.session.delete(ftype)
                db.session.commit()
                flash('Filament-Typ erfolgreich gelöscht.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Fehler beim Löschen: {e}', 'danger')
    else:
        flash('Filament-Typ nicht gefunden.', 'danger')
        
    return redirect(url_for('materials_bp.list_types'))


# --- FilamentSpool Routes ---

@materials_bp.route('/types/<int:type_id>/spools')
@login_required
def manage_spools(type_id):
    filament_type = db.session.get(FilamentType, type_id)
    if not filament_type:
        flash("Filament-Typ nicht gefunden.", "danger")
        return redirect(url_for('materials_bp.list_types'))
    
    printers = Printer.query.order_by(Printer.name).all()
    return render_template('materials/manage_spools.html', filament_type=filament_type, printers=printers)


@materials_bp.route('/spools/add', methods=['POST'])
@login_required
def add_spool():
    type_id = request.form.get('filament_type_id', type=int)
    if not type_id:
        flash("Kein Filament-Typ ausgewählt.", "danger")
        return redirect(request.referrer or url_for('materials_bp.list_filaments'))

    try:
        initial_weight = request.form.get('initial_weight_g', 1000, type=int)
        purchase_date_str = request.form.get('purchase_date')
        purchase_date = datetime.datetime.strptime(purchase_date_str, '%Y-%m-%d').date() if purchase_date_str else None

        new_spool = FilamentSpool(
            filament_type_id=type_id,
            initial_weight_g=initial_weight,
            current_weight_g=initial_weight,
            purchase_date=purchase_date,
            notes=request.form.get('notes')
        )
        db.session.add(new_spool)
        db.session.commit()
        flash(f"Neue Spule '{new_spool.short_id}' wurde erfolgreich hinzugefügt.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Hinzufügen der Spule: {e}", "danger")

    return redirect(request.referrer or url_for('materials_bp.list_filaments'))

@materials_bp.route('/spools/assign_to_printer', methods=['POST'])
@login_required
def assign_to_printer():
    """Weist eine Spule einem Drucker zu."""
    spool_id = request.form.get('spool_id', type=int)
    printer_id = request.form.get('printer_id', type=int)
    spool = db.session.get(FilamentSpool, spool_id)
    printer = db.session.get(Printer, printer_id)

    if not spool or not printer:
        flash("Spule oder Drucker nicht gefunden.", "danger")
        return redirect(request.referrer)

    try:
        # Alte Spule vom Drucker entfernen
        FilamentSpool.query.filter_by(assigned_to_printer_id=printer.id).update(
            {'is_in_use': False, 'assigned_to_printer_id': None}
        )
        # Neue Spule zuweisen
        spool.assigned_to_printer_id = printer.id
        spool.is_in_use = True
        spool.is_drying = False # Sicherheitshalber Trocknen beenden
        db.session.commit()
        flash(f"Spule '{spool.short_id}' wurde Drucker '{printer.name}' zugewiesen.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler bei der Zuweisung: {e}", "danger")
    
    return redirect(request.referrer or url_for('materials_bp.list_filaments'))

@materials_bp.route('/spools/return_to_storage/<int:spool_id>', methods=['POST'])
@login_required
def return_to_storage(spool_id):
    """Entfernt die Zuweisung einer Spule von einem Drucker."""
    spool = db.session.get(FilamentSpool, spool_id)
    if spool:
        try:
            spool.is_in_use = False
            spool.assigned_to_printer_id = None
            db.session.commit()
            flash(f'Spule {spool.short_id} wurde ins Lager zurückgebucht.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Zurückbuchen: {e}', 'danger')
    else:
        flash('Spule nicht gefunden.', 'danger')
    return redirect(request.referrer or url_for('materials_bp.list_filaments'))


# --- NEUE ROUTE ZUM LÖSCHEN EINER SPULE ---
@materials_bp.route('/spools/delete/<int:spool_id>', methods=['POST'])
@login_required
def delete_spool(spool_id):
    """Löscht eine einzelne Spule aus dem Inventar."""
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool:
        flash("Spule nicht gefunden.", "danger")
    elif spool.is_in_use:
        flash(f"Spule '{spool.short_id}' ist einem Drucker zugewiesen und kann nicht gelöscht werden.", "danger")
    else:
        try:
            db.session.delete(spool)
            db.session.commit()
            flash(f"Spule '{spool.short_id}' wurde erfolgreich gelöscht.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Löschen der Spule: {e}", "danger")
            
    # Redirect zurück zur vorherigen Seite, was in diesem Fall die 'manage_spools'-Seite sein sollte.
    return redirect(request.referrer or url_for('materials_bp.list_filaments'))


@materials_bp.route('/qrcode/<int:spool_id>')
@login_required
def qr_code(spool_id):
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool: return "Spool not found", 404
    qr_data = json.dumps({'sid': spool.short_id})
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


@materials_bp.route('/print_labels', methods=['POST'])
@login_required
def print_labels():
    spool_ids_str = request.form.get('spool_ids')
    if not spool_ids_str:
        flash("Keine Spulen zum Drucken ausgewählt.", "warning")
        return redirect(url_for('materials_bp.list_filaments'))
    
    spool_ids = [int(id) for id in spool_ids_str.split(',')]
    spools_to_print = FilamentSpool.query.filter(FilamentSpool.id.in_(spool_ids)).all()
    
    return render_template('materials/print_labels.html', spools=spools_to_print)

def update_type_from_form(ftype, form):
    """Hilfsfunktion zum Aktualisieren eines FilamentType-Objekts."""
    ftype.manufacturer = form.get('manufacturer')
    ftype.name = form.get('name')
    ftype.material_type = form.get('material_type', '').upper()
    ftype.color_hex = form.get('color_hex', '#FFFFFF')
    ftype.density_gcm3 = form.get('density_gcm3', type=float, default=1.24)
    ftype.diameter_mm = form.get('diameter_mm', type=float, default=1.75)
    ftype.cost_per_spool = form.get('cost_per_spool', type=float)
    ftype.spool_weight_g = form.get('spool_weight_g', type=int) or 1000
    ftype.reorder_level_g = form.get('reorder_level_g', type=int) or None
    ftype.notes = form.get('notes')
    ftype.print_settings = json.dumps({
        'nozzle_temp': form.get('nozzle_temp'),
        'bed_temp': form.get('bed_temp'),
        'print_speed': form.get('print_speed')
    })


# --- Filament-Trockner Routes ---

@materials_bp.route('/dryer')
@login_required
def dryer_view():
    drying_spools = FilamentSpool.query.filter_by(is_drying=True).order_by(FilamentSpool.drying_start_time).all()
    available_spools = FilamentSpool.query.filter_by(is_drying=False, is_in_use=False).join(FilamentType).order_by(FilamentType.manufacturer, FilamentType.name).all()
    return render_template('materials/dryer.html', drying_spools=drying_spools, available_spools=available_spools)

@materials_bp.route('/spools/start_drying', methods=['POST'])
@login_required
def start_drying():
    try:
        spool_id = request.form.get('spool_id', type=int)
        temp = request.form.get('drying_temp', type=int)
        humidity = request.form.get('drying_humidity', type=int)

        spool = db.session.get(FilamentSpool, spool_id)
        if not spool:
            flash("Spule nicht gefunden.", "danger")
            return redirect(url_for('materials_bp.dryer_view'))

        spool.is_drying = True
        spool.drying_start_time = datetime.datetime.utcnow()
        spool.drying_temp = temp
        spool.drying_humidity = humidity
        spool.is_in_use = False # Kann nicht gleichzeitig in Benutzung sein
        spool.assigned_to_printer_id = None
        db.session.commit()
        flash(f"Spule '{spool.short_id}' wurde zum Trockner hinzugefügt.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Starten des Trocknungsvorgangs: {e}", "danger")
    return redirect(url_for('materials_bp.dryer_view'))


@materials_bp.route('/spools/stop_drying/<int:spool_id>', methods=['POST'])
@login_required
def stop_drying(spool_id):
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool:
        flash("Spule nicht gefunden.", "danger")
        return redirect(url_for('materials_bp.dryer_view'))
    try:
        spool.is_drying = False
        spool.drying_start_time = None
        spool.drying_temp = None
        spool.drying_humidity = None
        db.session.commit()
        flash(f"Spule '{spool.short_id}' wurde aus dem Trockner entfernt.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Beenden des Trocknungsvorgangs: {e}", "danger")
    return redirect(url_for('materials_bp.dryer_view'))


@materials_bp.route('/assign_spool', methods=['POST'])
@login_required
def assign_spool():
    """Weist eine Spule einem Drucker zu (wird vom Dashboard aufgerufen)."""
    printer_id = request.form.get('printer_id')
    spool_id = request.form.get('spool_id')

    if not printer_id or not spool_id:
        flash("Drucker-ID oder Spulen-ID fehlt.", "danger")
        return redirect(url_for('jobs_bp.dashboard'))

    # Alte Spule vom Drucker entfernen (falls vorhanden)
    current_spool = FilamentSpool.query.filter_by(assigned_to_printer_id=printer_id, is_in_use=True).first()
    if current_spool:
        current_spool.is_in_use = False

    # Neue Spule zuweisen
    new_spool = db.session.get(FilamentSpool, int(spool_id))
    if new_spool:
        new_spool.assigned_to_printer_id = int(printer_id)
        new_spool.is_in_use = True
        flash(f"Spule '{new_spool.short_id}' wurde erfolgreich Drucker zugewiesen.", "success")
    else:
        flash("Ausgewählte Spule nicht gefunden.", "danger")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Zuweisen der Spule: {e}", "danger")

    return redirect(url_for('jobs_bp.dashboard'))