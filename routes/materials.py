# /routes/materials.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from extensions import db
from models import FilamentType, FilamentSpool, Printer, SystemSetting
from flask_login import login_required, current_user
import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, distinct
import qrcode
import base64
from io import BytesIO
import json
import io
import csv
import uuid
from collections import defaultdict

materials_bp = Blueprint('materials_bp', __name__, url_prefix='/materials')

# --- FilamentType Routes (Obergruppe) ---

@materials_bp.route('/dryer-dashboard')
@login_required
def dryer_dashboard():
    """Vereinfachte Trockner-Ansicht"""
    # Alle Spulen laden
    spools = FilamentSpool.query.join(FilamentType).filter(
        FilamentSpool.current_weight_g > 0
    ).order_by(
        FilamentType.manufacturer,
        FilamentType.name
    ).all()
    
    return render_template('materials/dryer_view.html', spools=spools)

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

@materials_bp.route('/consumption-analytics')
@login_required
def consumption_analytics():
    """Erweiterte Verbrauchsprognose-Ansicht"""
    # Parameter aus URL
    days = request.args.get('days', 30, type=int)
    material_filter = request.args.get('material', '')
    show_only_low = request.args.get('low_only', False, type=bool)
    
    # Alle Materialien für Filter-Dropdown
    all_materials = FilamentType.query.order_by(
        FilamentType.manufacturer, 
        FilamentType.name
    ).all()
    
    # Gefilterte Materialien
    materials_query = FilamentType.query
    if material_filter:
        materials_query = materials_query.filter(
            FilamentType.id == material_filter
        )
    
    materials = materials_query.order_by(
        FilamentType.manufacturer,
        FilamentType.name
    ).all()
    
    # Prognose-Daten berechnen
    forecasts = []
    for material in materials:
        total_weight = material.total_remaining_weight
        
        if total_weight <= 0:
            continue
            
        # Grundlegende Prognose
        forecast_data = {
            'material': material,
            'total_weight_g': total_weight,
            'total_spools': material.total_spool_count,
            'available_spools': material.available_spool_count,
            'reorder_level': material.reorder_level_g,
            'is_low_stock': total_weight <= (material.reorder_level_g or 0) if material.reorder_level_g else False
        }
        
        # Verbrauchsberechnung (vereinfacht)
        if material.reorder_level_g and material.reorder_level_g > 0:
            if total_weight <= material.reorder_level_g * 0.5:
                status = 'critical'
                estimated_days = round(total_weight / 50, 1)  # 50g/Tag Annahme
            elif total_weight <= material.reorder_level_g:
                status = 'warning'
                estimated_days = round(total_weight / 30, 1)  # 30g/Tag Annahme
            else:
                status = 'ok'
                estimated_days = round(total_weight / 20, 1)  # 20g/Tag Annahme
        else:
            status = 'unknown'
            estimated_days = round(total_weight / 25, 1)  # 25g/Tag Standard
        
        forecast_data.update({
            'status': status,
            'estimated_days_remaining': estimated_days,
            'estimated_weeks_remaining': round(estimated_days / 7, 1),
            'daily_consumption_estimate': round(total_weight / estimated_days, 1) if estimated_days > 0 else 0
        })
        
        # Filter: Nur niedrige Bestände
        if show_only_low and status not in ['critical', 'warning']:
            continue
            
        forecasts.append(forecast_data)
    
    # Sortierung nach Status (kritisch zuerst)
    status_order = {'critical': 0, 'warning': 1, 'ok': 2, 'unknown': 3}
    forecasts.sort(key=lambda x: (status_order.get(x['status'], 4), x['estimated_days_remaining']))
    
    return render_template('materials/consumption_analytics.html',
                         forecasts=forecasts,
                         all_materials=all_materials,
                         days=days,
                         material_filter=material_filter,
                         show_only_low=show_only_low)

# ======================================================================================
# VOLLSTÄNDIGE LAGERORT-VERWALTUNG - NEUE FUNKTIONEN
# ======================================================================================

@materials_bp.route('/storage-management')
@login_required
def storage_management():
    """Lagerort-Verwaltung für Filament-Spulen"""
    # URL-Parameter für Filter und Sortierung
    location_filter = request.args.get('location', '')
    material_filter = request.args.get('material', '')
    show_empty_locations = request.args.get('show_empty', 'true') == 'true'
    sort_by = request.args.get('sort', 'location')  # location, material, weight, date
    
    # Basis-Query für Spulen
    spools_query = FilamentSpool.query.join(FilamentType).filter(
        FilamentSpool.current_weight_g > 0
    )
    
    # Material-Filter anwenden
    if material_filter:
        spools_query = spools_query.filter(
            FilamentType.material_type.ilike(f'%{material_filter}%')
        )
    
    # Location-Filter anwenden
    if location_filter:
        spools_query = spools_query.filter(
            FilamentSpool.storage_location.ilike(f'%{location_filter}%')
        )
    
    # Sortierung anwenden
    if sort_by == 'material':
        spools_query = spools_query.order_by(FilamentType.manufacturer, FilamentType.name)
    elif sort_by == 'weight':
        spools_query = spools_query.order_by(FilamentSpool.current_weight_g.desc())
    elif sort_by == 'date':
        spools_query = spools_query.order_by(FilamentSpool.purchase_date.desc().nulls_last())
    else:  # location
        spools_query = spools_query.order_by(FilamentSpool.storage_location.asc().nulls_last())
    
    spools = spools_query.all()
    
    # Gruppierung nach Lagerort
    locations = defaultdict(list)
    unassigned_spools = []
    
    for spool in spools:
        if spool.storage_location and spool.storage_location.strip():
            locations[spool.storage_location].append(spool)
        else:
            unassigned_spools.append(spool)
    
    # Statistiken berechnen
    total_spools = len(spools)
    total_locations = len(locations)
    total_weight = sum(spool.current_weight_g for spool in spools)
    
    # Alle verfügbaren Lagerorte für Dropdown (inkl. gespeicherte aus SystemSettings)
    all_locations_from_spools = db.session.query(distinct(FilamentSpool.storage_location))\
        .filter(FilamentSpool.storage_location.isnot(None))\
        .filter(FilamentSpool.storage_location != '')\
        .order_by(FilamentSpool.storage_location).all()
    available_locations = [loc[0] for loc in all_locations_from_spools if loc[0]]
    
    # Zusätzlich gespeicherte Lagerorte aus SystemSettings hinzufügen
    try:
        locations_setting = SystemSetting.query.filter_by(key='storage_locations').first()
        if locations_setting:
            stored_locations = json.loads(locations_setting.value)
            for stored_loc in stored_locations:
                location_name = stored_loc.get('name')
                if location_name and location_name not in available_locations:
                    available_locations.append(location_name)
        available_locations.sort()
    except Exception as e:
        pass  # Falls JSON-Parsing fehlschlägt, ignorieren
    
    # Material-Typen für Filter
    material_types = db.session.query(distinct(FilamentType.material_type))\
        .order_by(FilamentType.material_type).all()
    available_materials = [mat[0] for mat in material_types if mat[0]]
    
    return render_template('materials/storage_management.html', 
                         locations=dict(locations), 
                         unassigned_spools=unassigned_spools,
                         available_locations=available_locations,
                         available_materials=available_materials,
                         total_spools=total_spools,
                         total_locations=total_locations,
                         total_weight=total_weight,
                         current_filters={
                             'location': location_filter,
                             'material': material_filter,
                             'show_empty': show_empty_locations,
                             'sort': sort_by
                         })

@materials_bp.route('/storage-management/locations')
@login_required
def get_storage_locations():
    """API: Gibt alle verfügbaren Lagerorte zurück"""
    locations = db.session.query(
        FilamentSpool.storage_location,
        func.count(FilamentSpool.id).label('spool_count'),
        func.sum(FilamentSpool.current_weight_g).label('total_weight')
    ).filter(
        FilamentSpool.storage_location.isnot(None),
        FilamentSpool.storage_location != '',
        FilamentSpool.current_weight_g > 0
    ).group_by(FilamentSpool.storage_location).all()
    
    location_data = []
    for location, count, weight in locations:
        location_data.append({
            'name': location,
            'spool_count': count,
            'total_weight_g': float(weight or 0),
            'utilization': 'unknown'  # Kann später erweitert werden
        })
    
    return jsonify({
        'status': 'success',
        'locations': location_data,
        'total_locations': len(location_data)
    })

@materials_bp.route('/storage-management/create-location', methods=['POST'])
@login_required
def create_storage_location():
    """API: Erstellt einen neuen Lagerort"""
    data = request.get_json()
    
    location_name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    capacity = data.get('capacity')  # Optional
    
    if not location_name:
        return jsonify({'status': 'error', 'message': 'Lagerort-Name ist erforderlich'}), 400
    
    # Prüfe ob Lagerort bereits existiert
    existing = FilamentSpool.query.filter_by(storage_location=location_name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Lagerort existiert bereits'}), 400
    
    try:
        # Da wir keine separate Locations-Tabelle haben, erstellen wir eine 
        # "Dummy"-Spule mit 0g Gewicht um den Lagerort zu registrieren
        # Diese wird in der UI nicht angezeigt (current_weight_g > 0 Filter)
        
        # Alternativ: Speichere in SystemSetting als JSON
        existing_locations_setting = SystemSetting.query.filter_by(key='storage_locations').first()
        
        if existing_locations_setting:
            try:
                locations_data = json.loads(existing_locations_setting.value)
            except:
                locations_data = []
        else:
            locations_data = []
            existing_locations_setting = SystemSetting(key='storage_locations', value='[]')
            db.session.add(existing_locations_setting)
        
        # Prüfe ob Location bereits in Settings existiert
        location_exists = any(loc.get('name') == location_name for loc in locations_data)
        if location_exists:
            return jsonify({'status': 'error', 'message': 'Lagerort existiert bereits'}), 400
        
        # Neue Location hinzufügen
        new_location = {
            'name': location_name,
            'description': description,
            'capacity': capacity,
            'created_at': datetime.datetime.utcnow().isoformat(),
            'created_by': current_user.id
        }
        
        locations_data.append(new_location)
        existing_locations_setting.value = json.dumps(locations_data)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Lagerort "{location_name}" erfolgreich erstellt',
            'location': new_location
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Fehler beim Erstellen: {str(e)}'}), 500

@materials_bp.route('/storage-management/move-spool', methods=['POST'])
@login_required
def move_spool():
    """API: Verschiebt eine Spule zu einem neuen Lagerort"""
    data = request.get_json()
    spool_id = data.get('spool_id')
    new_location = data.get('new_location')
    
    if new_location == 'unassigned':
        new_location = None
    
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool:
        return jsonify({'status': 'error', 'message': 'Spule nicht gefunden'}), 404
    
    try:
        old_location = spool.storage_location or 'Unzugewiesen'
        spool.storage_location = new_location
        
        # Log-Eintrag für Bewegung (vereinfacht)
        if not spool.usage_history:
            spool.usage_history = []
        
        if isinstance(spool.usage_history, str):
            import json
            try:
                spool.usage_history = json.loads(spool.usage_history)
            except:
                spool.usage_history = []
        
        movement_log = {
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'action': 'location_change',
            'old_location': old_location,
            'new_location': new_location or 'Unzugewiesen',
            'user_id': current_user.id
        }
        spool.usage_history.append(movement_log)
        
        # Nur die letzten 20 Einträge behalten
        spool.usage_history = spool.usage_history[-20:]
        
        db.session.commit()
        
        new_location_display = new_location or 'Unzugewiesen'
        return jsonify({
            'status': 'success', 
            'message': f'Spule {spool.short_id} von "{old_location}" nach "{new_location_display}" verschoben'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@materials_bp.route('/storage-management/bulk-move', methods=['POST'])
@login_required
def bulk_move_spools():
    """API: Verschiebt mehrere Spulen gleichzeitig"""
    data = request.get_json()
    spool_ids = data.get('spool_ids', [])
    new_location = data.get('new_location')
    
    if not spool_ids:
        return jsonify({'status': 'error', 'message': 'Keine Spulen ausgewählt'}), 400
    
    if new_location == 'unassigned':
        new_location = None
    
    try:
        spools = FilamentSpool.query.filter(FilamentSpool.id.in_(spool_ids)).all()
        moved_count = 0
        
        for spool in spools:
            old_location = spool.storage_location or 'Unzugewiesen'
            spool.storage_location = new_location
            
            # Log-Eintrag hinzufügen
            if not spool.usage_history:
                spool.usage_history = []
                
            if isinstance(spool.usage_history, str):
                import json
                try:
                    spool.usage_history = json.loads(spool.usage_history)
                except:
                    spool.usage_history = []
            
            movement_log = {
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'action': 'bulk_move',
                'old_location': old_location,
                'new_location': new_location or 'Unzugewiesen',
                'user_id': current_user.id
            }
            spool.usage_history.append(movement_log)
            spool.usage_history = spool.usage_history[-20:]
            
            moved_count += 1
        
        db.session.commit()
        
        new_location_display = new_location or 'Unzugewiesen'
        return jsonify({
            'status': 'success',
            'message': f'{moved_count} Spulen nach "{new_location_display}" verschoben'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@materials_bp.route('/storage-management/auto-organize', methods=['POST'])
@login_required
def auto_organize_spools():
    """API: Organisiert Spulen automatisch nach Material-Typ"""
    data = request.get_json()
    organization_type = data.get('type', 'material')  # material, manufacturer, color
    
    try:
        spools = FilamentSpool.query.join(FilamentType).filter(
            FilamentSpool.current_weight_g > 0,
            FilamentSpool.is_in_use == False
        ).all()
        
        moved_count = 0
        
        for spool in spools:
            if organization_type == 'material':
                new_location = f"MAT-{spool.filament_type.material_type}"
            elif organization_type == 'manufacturer':
                new_location = f"MFG-{spool.filament_type.manufacturer[:3].upper()}"
            elif organization_type == 'color':
                # Vereinfachte Farbgruppierung
                color_hex = spool.filament_type.color_hex.upper()
                if color_hex in ['#FFFFFF', '#F5F5F5']:
                    color_group = 'WHITE'
                elif color_hex in ['#000000', '#2F2F2F']:
                    color_group = 'BLACK'
                elif 'FF' in color_hex[:3]:
                    color_group = 'RED'
                elif '00FF' in color_hex:
                    color_group = 'GREEN'
                elif 'FF' in color_hex[4:]:
                    color_group = 'BLUE'
                else:
                    color_group = 'OTHER'
                new_location = f"COL-{color_group}"
            else:
                continue
            
            old_location = spool.storage_location
            spool.storage_location = new_location
            
            # Log-Eintrag
            if not spool.usage_history:
                spool.usage_history = []
                
            if isinstance(spool.usage_history, str):
                import json
                try:
                    spool.usage_history = json.loads(spool.usage_history)
                except:
                    spool.usage_history = []
            
            movement_log = {
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'action': 'auto_organize',
                'organization_type': organization_type,
                'old_location': old_location or 'Unzugewiesen',
                'new_location': new_location,
                'user_id': current_user.id
            }
            spool.usage_history.append(movement_log)
            spool.usage_history = spool.usage_history[-20:]
            
            moved_count += 1
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'{moved_count} Spulen automatisch nach {organization_type} organisiert',
            'moved_count': moved_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@materials_bp.route('/storage-management/search-spool', methods=['POST'])
@login_required
def search_spool():
    """API: Sucht eine Spule nach verschiedenen Kriterien"""
    data = request.get_json()
    search_term = data.get('search_term', '').strip()
    search_type = data.get('search_type', 'any')  # any, short_id, material, location
    
    if not search_term:
        return jsonify({'status': 'error', 'message': 'Suchbegriff erforderlich'}), 400
    
    # Basis-Query
    query = FilamentSpool.query.join(FilamentType).filter(
        FilamentSpool.current_weight_g > 0
    )
    
    # Such-Filter anwenden
    if search_type == 'short_id':
        query = query.filter(FilamentSpool.short_id.ilike(f'%{search_term}%'))
    elif search_type == 'material':
        query = query.filter(
            (FilamentType.name.ilike(f'%{search_term}%')) |
            (FilamentType.manufacturer.ilike(f'%{search_term}%')) |
            (FilamentType.material_type.ilike(f'%{search_term}%'))
        )
    elif search_type == 'location':
        query = query.filter(FilamentSpool.storage_location.ilike(f'%{search_term}%'))
    else:  # any
        query = query.filter(
            (FilamentSpool.short_id.ilike(f'%{search_term}%')) |
            (FilamentType.name.ilike(f'%{search_term}%')) |
            (FilamentType.manufacturer.ilike(f'%{search_term}%')) |
            (FilamentSpool.storage_location.ilike(f'%{search_term}%'))
        )
    
    spools = query.limit(20).all()  # Limit für Performance
    
    results = []
    for spool in spools:
        results.append({
            'id': spool.id,
            'short_id': spool.short_id,
            'material': f"{spool.filament_type.manufacturer} {spool.filament_type.name}",
            'material_type': spool.filament_type.material_type,
            'color': spool.filament_type.color_hex,
            'weight_g': spool.current_weight_g,
            'location': spool.storage_location or 'Unzugewiesen',
            'is_in_use': spool.is_in_use
        })
    
    return jsonify({
        'status': 'success',
        'results': results,
        'total_found': len(results),
        'search_term': search_term,
        'search_type': search_type
    })

@materials_bp.route('/storage-management/export', methods=['GET'])
@login_required
def export_storage_layout():
    """Exportiert das aktuelle Lager-Layout als CSV"""
    # Parameter
    format_type = request.args.get('format', 'csv')  # csv, json
    include_empty = request.args.get('include_empty', 'false') == 'true'
    
    # Daten sammeln
    spools = FilamentSpool.query.join(FilamentType).filter(
        FilamentSpool.current_weight_g > 0 if not include_empty else True
    ).order_by(
        FilamentSpool.storage_location.asc().nulls_last(),
        FilamentType.manufacturer,
        FilamentType.name
    ).all()
    
    if format_type == 'json':
        # JSON Export
        export_data = {
            'export_date': datetime.datetime.utcnow().isoformat(),
            'total_spools': len(spools),
            'spools': []
        }
        
        for spool in spools:
            export_data['spools'].append({
                'short_id': spool.short_id,
                'material': f"{spool.filament_type.manufacturer} {spool.filament_type.name}",
                'material_type': spool.filament_type.material_type,
                'color': spool.filament_type.color_hex,
                'weight_g': spool.current_weight_g,
                'storage_location': spool.storage_location,
                'purchase_date': spool.purchase_date.isoformat() if spool.purchase_date else None,
                'is_in_use': spool.is_in_use
            })
        
        response = jsonify(export_data)
        response.headers['Content-Disposition'] = f'attachment; filename=storage_layout_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        return response
    
    else:
        # CSV Export
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Spulen-ID', 'Material', 'Typ', 'Hersteller', 'Farbe', 
            'Gewicht (g)', 'Lagerort', 'Kaufdatum', 'In Benutzung', 'Notizen'
        ])
        
        # Daten
        for spool in spools:
            writer.writerow([
                spool.short_id,
                spool.filament_type.name,
                spool.filament_type.material_type,
                spool.filament_type.manufacturer,
                spool.filament_type.color_hex,
                spool.current_weight_g,
                spool.storage_location or 'Unzugewiesen',
                spool.purchase_date.strftime('%Y-%m-%d') if spool.purchase_date else '',
                'Ja' if spool.is_in_use else 'Nein',
                spool.notes or ''
            ])
        
        output.seek(0)
        
        # Response erstellen
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=lager_layout_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        
        return response

@materials_bp.route('/storage-management/get-stored-locations')
@login_required
def get_stored_locations():
    """Debug: Zeigt alle gespeicherten Lagerorte aus SystemSettings"""
    try:
        locations_setting = SystemSetting.query.filter_by(key='storage_locations').first()
        if locations_setting:
            stored_locations = json.loads(locations_setting.value)
            return jsonify({
                'status': 'success',
                'stored_locations': stored_locations,
                'count': len(stored_locations)
            })
        else:
            return jsonify({
                'status': 'success',
                'stored_locations': [],
                'count': 0,
                'message': 'Keine gespeicherten Lagerorte gefunden'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Fehler beim Laden: {str(e)}'
        }), 500

@materials_bp.route('/storage-management/delete-stored-location/<location_name>', methods=['DELETE'])
@login_required
def delete_stored_location(location_name):
    """Löscht einen gespeicherten Lagerort aus den SystemSettings"""
    try:
        locations_setting = SystemSetting.query.filter_by(key='storage_locations').first()
        if not locations_setting:
            return jsonify({'status': 'error', 'message': 'Keine gespeicherten Lagerorte gefunden'}), 404
        
        stored_locations = json.loads(locations_setting.value)
        
        # Location finden und entfernen
        original_count = len(stored_locations)
        stored_locations = [loc for loc in stored_locations if loc.get('name') != location_name]
        
        if len(stored_locations) == original_count:
            return jsonify({'status': 'error', 'message': 'Lagerort nicht gefunden'}), 404
        
        locations_setting.value = json.dumps(stored_locations)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Lagerort "{location_name}" gelöscht',
            'remaining_count': len(stored_locations)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Fehler beim Löschen: {str(e)}'}), 500
    """Setzt alle Lagerort-Zuweisungen zurück"""
    data = request.get_json()
    confirm = data.get('confirm', False)
    
    if not confirm:
        return jsonify({'status': 'error', 'message': 'Bestätigung erforderlich'}), 400
    
    try:
        # Alle Spulen auf unzugewiesen setzen
        spools = FilamentSpool.query.filter(
            FilamentSpool.storage_location.isnot(None)
        ).all()
        
        reset_count = 0
        for spool in spools:
            old_location = spool.storage_location
            spool.storage_location = None
            
            # Log-Eintrag
            if not spool.usage_history:
                spool.usage_history = []
                
            if isinstance(spool.usage_history, str):
                import json
                try:
                    spool.usage_history = json.loads(spool.usage_history)
                except:
                    spool.usage_history = []
            
            reset_log = {
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'action': 'layout_reset',
                'old_location': old_location,
                'new_location': None,
                'user_id': current_user.id
            }
            spool.usage_history.append(reset_log)
            spool.usage_history = spool.usage_history[-20:]
            
            reset_count += 1
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Layout zurückgesetzt. {reset_count} Spulen sind jetzt unzugewiesen.',
            'reset_count': reset_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

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