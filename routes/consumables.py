# /routes/consumables.py
import os
import uuid
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from extensions import db
from models import Consumable, Printer, ConsumableCategory, HazardSymbol
from flask_login import login_required
import datetime

consumables_bp = Blueprint('consumables_bp', __name__, url_prefix='/consumables')

@consumables_bp.route('/')
@login_required
def list_consumables():
    """Zeigt eine Liste aller Verbrauchsmaterialien an."""
    category_filter = request.args.get('category')
    status_filter = request.args.get('status')
    search_query = request.args.get('search', '').strip()
    
    query = Consumable.query
    
    # Kategorie-Filter
    if category_filter and category_filter != 'all':
        try:
            query = query.filter(Consumable.category == ConsumableCategory(category_filter))
        except ValueError:
            pass
    
    # Status-Filter
    if status_filter:
        if status_filter == 'low_stock':
            query = query.filter(
                Consumable.reorder_level.isnot(None),
                Consumable.stock_level <= Consumable.reorder_level
            )
        elif status_filter == 'critical':
            query = query.filter(
                Consumable.min_stock.isnot(None),
                Consumable.stock_level < Consumable.min_stock
            )
        elif status_filter == 'expired':
            query = query.filter(
                Consumable.has_expiry == True,
                Consumable.expiry_date < datetime.date.today()
            )
        elif status_filter == 'expiring':
            expiry_threshold = datetime.date.today() + datetime.timedelta(days=30)
            query = query.filter(
                Consumable.has_expiry == True,
                Consumable.expiry_date <= expiry_threshold,
                Consumable.expiry_date >= datetime.date.today()
            )
    
    # Suchfilter
    if search_query:
        query = query.filter(
            db.or_(
                Consumable.name.ilike(f'%{search_query}%'),
                Consumable.manufacturer.ilike(f'%{search_query}%'),
                Consumable.article_number.ilike(f'%{search_query}%')
            )
        )
    
    consumables = query.order_by(Consumable.category, Consumable.name).all()
    categories = ConsumableCategory
    
    return render_template('consumables/list.html', 
                         consumables=consumables, 
                         categories=categories,
                         current_category=category_filter,
                         current_status=status_filter,
                         search_query=search_query)

@consumables_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_consumable():
    """Fügt ein neues Verbrauchsmaterial hinzu."""
    if request.method == 'POST':
        try:
            # Kategorie richtig konvertieren
            category_name = request.form.get('category', 'OTHER')
            try:
                category = ConsumableCategory[category_name]  # Verwende Name statt Value
            except KeyError:
                category = ConsumableCategory.OTHER
            
            # Basis-Felder
            new_consumable = Consumable(
                name=request.form['name'],
                category=category,
                description=request.form.get('description'),
                usage_description=request.form.get('usage_description'),
                stock_level=request.form.get('stock_level', 0, type=int),
                unit=request.form.get('unit', 'Stück'),
                min_stock=request.form.get('min_stock', type=int) or None,
                reorder_level=request.form.get('reorder_level', type=int) or None,
                max_stock=request.form.get('max_stock', type=int) or None,
                storage_location=request.form.get('storage_location'),
                manufacturer=request.form.get('manufacturer'),
                supplier=request.form.get('supplier'),
                article_number=request.form.get('article_number'),
                ean=request.form.get('ean'),
                unit_price=request.form.get('unit_price', type=float) or None,
                currency=request.form.get('currency', 'EUR'),
                has_expiry=bool(request.form.get('has_expiry')),
                datasheet_url=request.form.get('datasheet_url'),
                compatibility_tags=request.form.get('compatibility_tags'),
                notes=request.form.get('notes')
            )
            
            # Haltbarkeitsdatum
            if new_consumable.has_expiry:
                expiry_str = request.form.get('expiry_date')
                if expiry_str:
                    new_consumable.expiry_date = datetime.datetime.strptime(expiry_str, '%Y-%m-%d').date()
            
            # Letzte Bestellung
            last_ordered_str = request.form.get('last_ordered_date')
            if last_ordered_str:
                new_consumable.last_ordered_date = datetime.datetime.strptime(last_ordered_str, '%Y-%m-%d').date()
            
            new_consumable.last_order_quantity = request.form.get('last_order_quantity', type=int) or None
            
            # Gefahrensymbole (Checkboxen)
            hazard_symbols = []
            for symbol in HazardSymbol:
                if request.form.get(f'hazard_{symbol.name}'):
                    hazard_symbols.append(symbol.value)
            new_consumable.hazard_symbols = hazard_symbols if hazard_symbols else None
            
            # Sicherheitshinweise (Textarea -> Liste)
            safety_warnings_text = request.form.get('safety_warnings', '').strip()
            if safety_warnings_text:
                new_consumable.safety_warnings = [
                    line.strip() for line in safety_warnings_text.split('\n') if line.strip()
                ]
            
            # Technische Spezifikationen (JSON-Eingabe)
            specifications = {}
            spec_keys = request.form.getlist('spec_key[]')
            spec_values = request.form.getlist('spec_value[]')
            for key, value in zip(spec_keys, spec_values):
                if key.strip() and value.strip():
                    specifications[key.strip()] = value.strip()
            new_consumable.specifications = specifications if specifications else None
            
            # Drucker-Zuordnung
            printer_ids = request.form.getlist('printer_ids')
            if printer_ids:
                printers = Printer.query.filter(Printer.id.in_(printer_ids)).all()
                new_consumable.compatible_printers = printers
            
            # Bildupload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                    
                    # Verzeichnis erstellen falls nicht vorhanden
                    consumables_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'consumables')
                    os.makedirs(consumables_folder, exist_ok=True)
                    
                    file_path = os.path.join(consumables_folder, unique_filename)
                    file.save(file_path)
                    new_consumable.image_filename = unique_filename
                elif file.filename != '':
                    flash('Ungültiger Bilddateityp.', 'warning')
            
            db.session.add(new_consumable)
            db.session.commit()
            flash('Verbrauchsmaterial erfolgreich hinzugefügt.', 'success')
            return redirect(url_for('consumables_bp.list_consumables'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Hinzufügen: {e}', 'danger')
    
    # GET Request - zeige Formular
    printers = Printer.query.order_by(Printer.name).all()
    categories = ConsumableCategory
    hazard_symbols = HazardSymbol
    return render_template('consumables/add_edit.html', 
                         consumable=None, 
                         printers=printers,
                         categories=categories,
                         hazard_symbols=hazard_symbols)

@consumables_bp.route('/edit/<int:consumable_id>', methods=['GET', 'POST'])
@login_required
def edit_consumable(consumable_id):
    """Bearbeitet ein bestehendes Verbrauchsmaterial."""
    consumable = db.session.get(Consumable, consumable_id)
    if not consumable:
        flash('Verbrauchsmaterial nicht gefunden.', 'danger')
        return redirect(url_for('consumables_bp.list_consumables'))

    if request.method == 'POST':
        try:
            # Kategorie richtig konvertieren
            category_name = request.form.get('category', 'OTHER')
            try:
                category = ConsumableCategory[category_name]
            except KeyError:
                category = ConsumableCategory.OTHER
            
            # Basis-Felder aktualisieren
            consumable.name = request.form['name']
            consumable.category = category
            consumable.description = request.form.get('description')
            consumable.usage_description = request.form.get('usage_description')
            consumable.stock_level = request.form.get('stock_level', 0, type=int)
            consumable.unit = request.form.get('unit', 'Stück')
            consumable.min_stock = request.form.get('min_stock', type=int) or None
            consumable.reorder_level = request.form.get('reorder_level', type=int) or None
            consumable.max_stock = request.form.get('max_stock', type=int) or None
            consumable.storage_location = request.form.get('storage_location')
            consumable.manufacturer = request.form.get('manufacturer')
            consumable.supplier = request.form.get('supplier')
            consumable.article_number = request.form.get('article_number')
            consumable.ean = request.form.get('ean')
            consumable.unit_price = request.form.get('unit_price', type=float) or None
            consumable.currency = request.form.get('currency', 'EUR')
            consumable.has_expiry = bool(request.form.get('has_expiry'))
            consumable.datasheet_url = request.form.get('datasheet_url')
            consumable.compatibility_tags = request.form.get('compatibility_tags')
            consumable.notes = request.form.get('notes')
            
            # Haltbarkeitsdatum
            if consumable.has_expiry:
                expiry_str = request.form.get('expiry_date')
                if expiry_str:
                    consumable.expiry_date = datetime.datetime.strptime(expiry_str, '%Y-%m-%d').date()
            else:
                consumable.expiry_date = None
            
            # Letzte Bestellung
            last_ordered_str = request.form.get('last_ordered_date')
            if last_ordered_str:
                consumable.last_ordered_date = datetime.datetime.strptime(last_ordered_str, '%Y-%m-%d').date()
            else:
                consumable.last_ordered_date = None
            
            consumable.last_order_quantity = request.form.get('last_order_quantity', type=int) or None
            
            # Gefahrensymbole
            hazard_symbols = []
            for symbol in HazardSymbol:
                if request.form.get(f'hazard_{symbol.name}'):
                    hazard_symbols.append(symbol.value)
            consumable.hazard_symbols = hazard_symbols if hazard_symbols else None
            
            # Sicherheitshinweise
            safety_warnings_text = request.form.get('safety_warnings', '').strip()
            if safety_warnings_text:
                consumable.safety_warnings = [
                    line.strip() for line in safety_warnings_text.split('\n') if line.strip()
                ]
            else:
                consumable.safety_warnings = None
            
            # Technische Spezifikationen
            specifications = {}
            spec_keys = request.form.getlist('spec_key[]')
            spec_values = request.form.getlist('spec_value[]')
            for key, value in zip(spec_keys, spec_values):
                if key.strip() and value.strip():
                    specifications[key.strip()] = value.strip()
            consumable.specifications = specifications if specifications else None
            
            # Drucker-Zuordnung aktualisieren
            printer_ids = request.form.getlist('printer_ids')
            if printer_ids:
                printers = Printer.query.filter(Printer.id.in_(printer_ids)).all()
                consumable.compatible_printers = printers
            else:
                consumable.compatible_printers = []
            
            # Bildupload
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Altes Bild löschen
                    if consumable.image_filename:
                        old_image_path = os.path.join(
                            current_app.config['UPLOAD_FOLDER'], 
                            'consumables', 
                            consumable.image_filename
                        )
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    
                    filename = secure_filename(file.filename)
                    unique_filename = f"{consumable_id}_{uuid.uuid4().hex[:8]}_{filename}"
                    
                    consumables_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'consumables')
                    os.makedirs(consumables_folder, exist_ok=True)
                    
                    file_path = os.path.join(consumables_folder, unique_filename)
                    file.save(file_path)
                    consumable.image_filename = unique_filename
                elif file.filename != '':
                    flash('Ungültiger Bilddateityp.', 'warning')
            
            db.session.commit()
            flash('Verbrauchsmaterial erfolgreich aktualisiert.', 'success')
            return redirect(url_for('consumables_bp.view_consumable', consumable_id=consumable_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Aktualisieren: {e}', 'danger')

    # GET Request - zeige Formular
    printers = Printer.query.order_by(Printer.name).all()
    categories = ConsumableCategory
    hazard_symbols = HazardSymbol
    return render_template('consumables/add_edit.html', 
                         consumable=consumable, 
                         printers=printers,
                         categories=categories,
                         hazard_symbols=hazard_symbols)

@consumables_bp.route('/view/<int:consumable_id>')
@login_required
def view_consumable(consumable_id):
    """Zeigt Detailansicht eines Verbrauchsmaterials."""
    consumable = db.session.get(Consumable, consumable_id)
    if not consumable:
        flash('Verbrauchsmaterial nicht gefunden.', 'danger')
        return redirect(url_for('consumables_bp.list_consumables'))
    
    return render_template('consumables/view.html', consumable=consumable)

@consumables_bp.route('/delete/<int:consumable_id>', methods=['POST'])
@login_required
def delete_consumable(consumable_id):
    """Löscht ein Verbrauchsmaterial."""
    consumable = db.session.get(Consumable, consumable_id)
    if consumable:
        try:
            # Bild löschen falls vorhanden
            if consumable.image_filename:
                image_path = os.path.join(
                    current_app.config['UPLOAD_FOLDER'], 
                    'consumables', 
                    consumable.image_filename
                )
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            db.session.delete(consumable)
            db.session.commit()
            flash('Verbrauchsmaterial erfolgreich gelöscht.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Löschen: {e}', 'danger')
    else:
        flash('Verbrauchsmaterial nicht gefunden.', 'danger')
        
    return redirect(url_for('consumables_bp.list_consumables'))

@consumables_bp.route('/adjust_stock/<int:consumable_id>', methods=['POST'])
@login_required
def adjust_stock(consumable_id):
    """Passt den Lagerbestand an."""
    consumable = db.session.get(Consumable, consumable_id)
    if not consumable:
        flash('Verbrauchsmaterial nicht gefunden.', 'danger')
        return redirect(url_for('consumables_bp.list_consumables'))
    
    try:
        adjustment = request.form.get('adjustment', type=int)
        if adjustment is not None:
            consumable.stock_level = max(0, consumable.stock_level + adjustment)
            db.session.commit()
            flash(f'Lagerbestand erfolgreich angepasst. Neuer Bestand: {consumable.stock_level} {consumable.unit}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fehler beim Anpassen des Lagerbestands: {e}', 'danger')
    
    return redirect(url_for('consumables_bp.view_consumable', consumable_id=consumable_id))

# --- Hilfsfunktionen ---
def allowed_file(filename):
    """Überprüft, ob eine Datei eine zulässige Bild-Endung hat."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS