import os
from flask import Blueprint, render_template, request, jsonify, flash, current_app
from extensions import db
from models import LayoutItem, Printer, LayoutItemType
from flask_login import login_required

layout_editor_bp = Blueprint('layout_editor_bp', __name__, template_folder='../templates/digital_twin')

def get_available_models():
    """Sucht im static/models-Ordner nach verfügbaren 3D-Modellen."""
    models_path = os.path.join(current_app.static_folder, 'models')
    if not os.path.exists(models_path):
        return []
    
    supported_extensions = ('.glb', '.gltf')
    models = [f for f in os.listdir(models_path) if f.endswith(supported_extensions)]
    return models

@layout_editor_bp.route('/layout-editor')
@login_required
def editor():
    """Zeigt den 3D-Layout-Editor an."""
    items = LayoutItem.query.all()
    printers = Printer.query.all()
    available_models = get_available_models()
    return render_template('editor.html',
                           items=items,
                           printers=printers,
                           LayoutItemType=LayoutItemType,
                           available_models=available_models)

@layout_editor_bp.route('/layout-editor/items', methods=['GET'])
@login_required
def get_items():
    """Gibt alle Layout-Items als JSON zurück."""
    items = LayoutItem.query.all()
    items_data = []
    for item in items:
        items_data.append({
            'id': item.id,
            'name': item.name,
            'item_type': item.item_type.value,
            'model_path': item.model_path,
            'position_x': item.position_x,
            'position_y': item.position_y,
            'position_z': item.position_z,
            'rotation_x': item.rotation_x,
            'rotation_y': item.rotation_y,
            'rotation_z': item.rotation_z,
            'scale_x': item.scale_x,
            'scale_y': item.scale_y,
            'scale_z': item.scale_z,
            'is_visible': item.is_visible,
            'color': item.color,
            'printer_id': item.printer_id
        })
    return jsonify(items_data)

@layout_editor_bp.route('/layout-editor/save', methods=['POST'])
@login_required
def save_layout():
    """Speichert die Position, Rotation und Skalierung aller Layout-Items."""
    data = request.json
    if not isinstance(data, list):
        return jsonify({'status': 'error', 'message': 'Invalid data format, expected a list of items.'}), 400

    try:
        for item_data in data:
            item = db.session.get(LayoutItem, item_data['id'])
            if item:
                item.position_x = item_data['position']['x']
                item.position_y = item_data['position']['y']
                item.position_z = item_data['position']['z']
                item.rotation_x = item_data['rotation']['x']
                item.rotation_y = item_data['rotation']['y']
                item.rotation_z = item_data['rotation']['z']
                item.scale_x = item_data['scale']['x']
                item.scale_y = item_data['scale']['y']
                item.scale_z = item_data['scale']['z']
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Layout wurde erfolgreich gespeichert.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@layout_editor_bp.route('/layout-editor/item/add', methods=['POST'])
@login_required
def add_item():
    """Fügt ein neues Item zum Layout hinzu."""
    try:
        model_filename = request.form.get('model_path')
        if not model_filename:
            return jsonify({'status': 'error', 'message': 'Keine Modelldatei ausgewählt.'}), 400
            
        model_path = os.path.basename(model_filename)

        new_item = LayoutItem(
            name=request.form.get('name'),
            item_type=LayoutItemType[request.form.get('item_type')],
            model_path=model_path,
            color=request.form.get('color') if request.form.get('color') else None,
            printer_id=int(request.form.get('printer_id')) if request.form.get('printer_id') else None
        )
        db.session.add(new_item)
        db.session.commit()

        response_item = {
            'id': new_item.id,
            'name': new_item.name,
            'item_type': new_item.item_type.value,
            'model_path': new_item.model_path,
            'position_x': new_item.position_x,
            'position_y': new_item.position_y,
            'position_z': new_item.position_z,
            'rotation_x': new_item.rotation_x,
            'rotation_y': new_item.rotation_y,
            'rotation_z': new_item.rotation_z,
            'scale_x': new_item.scale_x,
            'scale_y': new_item.scale_y,
            'scale_z': new_item.scale_z,
            'color': new_item.color,
            'printer_id': new_item.printer_id,
            'is_visible': new_item.is_visible
        }
        return jsonify({'status': 'success', 'message': 'Objekt erfolgreich hinzugefügt.', 'item': response_item})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fehler beim Hinzufügen des Layout-Items: {e}")
        return jsonify({'status': 'error', 'message': 'Ein interner Fehler ist aufgetreten.'}), 500

@layout_editor_bp.route('/layout-editor/item/<int:item_id>/update', methods=['POST'])
@login_required
def update_item(item_id):
    """Aktualisiert die Eigenschaften eines Items."""
    item = db.session.get(LayoutItem, item_id)
    if not item:
        return jsonify({'status': 'error', 'message': 'Item not found'}), 404
    try:
        item.name = request.form.get('name')
        color = request.form.get('color')
        item.color = color if color else None
        printer_id = request.form.get('printer_id')
        item.printer_id = int(printer_id) if printer_id and printer_id != 'None' else None
        is_visible = request.form.get('is_visible')
        item.is_visible = is_visible == 'on'

        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'Item updated successfully.',
            'item': {
                'id': item.id, 'name': item.name, 'color': item.color,
                'printer_id': item.printer_id, 'is_visible': item.is_visible
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@layout_editor_bp.route('/layout-editor/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    """Löscht ein Item aus dem Layout."""
    item = db.session.get(LayoutItem, item_id)
    if not item:
        return jsonify({'status': 'error', 'message': 'Item not found'}), 404
    try:
        db.session.delete(item)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Item deleted successfully.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500