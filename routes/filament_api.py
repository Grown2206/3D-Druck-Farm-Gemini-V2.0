from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from extensions import db, socketio
from models import FilamentType, FilamentSpool, Job, JobStatus, GCodeFile, Printer
import qrcode
import io
import base64
from datetime import datetime, timedelta, date
import json
from sqlalchemy import func, desc

filament_api_bp = Blueprint('filament_api_bp', __name__, url_prefix='/api/filament')

@filament_api_bp.route('/drying-status')
@login_required
def get_drying_status():
    """Gibt den Status aller aktiven Trocknungssessions zurück"""
    # Verwende das bestehende is_drying Feld
    active_spools = FilamentSpool.query.filter_by(is_drying=True).all()
    
    sessions_data = []
    for spool in active_spools:
        remaining_minutes = 0
        progress = 100
        
        # Berechne verbleibende Zeit falls drying_end_time gesetzt ist
        if spool.drying_end_time:
            remaining_seconds = (spool.drying_end_time - datetime.utcnow()).total_seconds()
            remaining_minutes = max(0, int(remaining_seconds / 60))
            
            if spool.drying_start_time:
                total_seconds = (spool.drying_end_time - spool.drying_start_time).total_seconds()
                elapsed_seconds = (datetime.utcnow() - spool.drying_start_time).total_seconds()
                progress = min(100, max(0, int((elapsed_seconds / total_seconds) * 100)))
        
        sessions_data.append({
            'id': spool.id,
            'spool': {
                'id': spool.id,
                'short_id': spool.short_id,
                'material': f"{spool.filament_type.manufacturer} {spool.filament_type.name}",
                'color': spool.filament_type.color_hex
            },
            'temperature': spool.drying_temp or 60,
            'start_time': spool.drying_start_time.isoformat() if spool.drying_start_time else datetime.utcnow().isoformat(),
            'end_time': spool.drying_end_time.isoformat() if spool.drying_end_time else datetime.utcnow().isoformat(),
            'remaining_minutes': remaining_minutes,
            'progress_percentage': progress,
            'is_overdue': remaining_minutes == 0 and spool.drying_end_time and spool.drying_end_time < datetime.utcnow(),
            'user': 'System'
        })
    
    return jsonify({
        'status': 'success',
        'active_sessions': sessions_data,
        'total_active': len(sessions_data)
    })

@filament_api_bp.route('/start-drying', methods=['POST'])
@login_required
def start_drying():
    """Startet eine Trocknungssession für eine Spule"""
    data = request.get_json()
    
    spool_id = data.get('spool_id')
    temperature = data.get('temperature')
    duration_hours = data.get('duration_hours')
    notes = data.get('notes', '')
    
    if not all([spool_id, temperature, duration_hours]):
        return jsonify({'status': 'error', 'message': 'Fehlende Parameter'}), 400
    
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool:
        return jsonify({'status': 'error', 'message': 'Spule nicht gefunden'}), 404
    
    try:
        session = spool.start_drying_session(
            temperature=int(temperature),
            duration_hours=int(duration_hours),
            user_id=current_user.id,
            notes=notes
        )
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Trocknungssession für {spool.short_id} gestartet',
            'session_id': session.id,
            'end_time': spool.drying_end_time.isoformat() if spool.drying_end_time else None
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@filament_api_bp.route('/complete-drying/<int:session_id>', methods=['POST'])
@login_required
def complete_drying(session_id):
    """Beendet eine Trocknungssession"""
    spool = db.session.get(FilamentSpool, session_id)
    if not spool:
        return jsonify({'status': 'error', 'message': 'Spule nicht gefunden'}), 404
    
    try:
        spool.complete_drying_session()
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Trocknung für {spool.short_id} abgeschlossen'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@filament_api_bp.route('/material-details/<int:material_id>')
@login_required
def get_material_details(material_id):
    """Liefert detaillierte Informationen über ein Material"""
    material = db.session.get(FilamentType, material_id)
    if not material:
        return jsonify({'status': 'error', 'message': 'Material nicht gefunden'}), 404
    
    try:
        # Bestandsinformationen
        total_spools = material.spools.count()
        available_spools = material.spools.filter(
            FilamentSpool.is_in_use == False,
            FilamentSpool.current_weight_g > 0
        ).count()
        
        in_use_spools = material.spools.filter_by(is_in_use=True).count()
        empty_spools = material.spools.filter(FilamentSpool.current_weight_g <= 0).count()
        
        # Lagerorte sammeln
        locations = db.session.query(FilamentSpool.storage_location)\
            .filter(FilamentSpool.filament_type_id == material_id)\
            .filter(FilamentSpool.storage_location.isnot(None))\
            .distinct().all()
        locations_list = [loc[0] for loc in locations if loc[0]]
        
        # Verbrauchsstatistiken
        # Letzter Verbrauch aus abgeschlossenen Jobs
        last_usage_job = Job.query\
            .filter_by(required_filament_type_id=material_id, status=JobStatus.COMPLETED)\
            .order_by(desc(Job.completed_at))\
            .first()
        
        last_usage_date = last_usage_job.completed_at if last_usage_job else None
        
        # Berechne durchschnittlichen Verbrauch pro Tag
        # Jobs der letzten 30 Tage
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_jobs = Job.query\
            .join(GCodeFile)\
            .filter(
                Job.required_filament_type_id == material_id,
                Job.status == JobStatus.COMPLETED,
                Job.completed_at >= thirty_days_ago
            ).all()
        
        total_consumption_30d = sum(job.gcode_file.material_needed_g or 0 for job in recent_jobs)
        avg_consumption_per_day = total_consumption_30d / 30 if total_consumption_30d > 0 else 0
        
        # Gesamtverbrauch aller Zeit
        all_jobs = Job.query\
            .join(GCodeFile)\
            .filter(
                Job.required_filament_type_id == material_id,
                Job.status == JobStatus.COMPLETED
            ).all()
        
        total_consumption_all_time = sum(job.gcode_file.material_needed_g or 0 for job in all_jobs)
        total_jobs_count = len(all_jobs)
        
        # Aktuelle Druckjobs mit diesem Material
        active_jobs = Job.query.filter(
            Job.required_filament_type_id == material_id,
            Job.status.in_([JobStatus.PRINTING, JobStatus.QUEUED, JobStatus.ASSIGNED])
        ).count()
        
        # Prognose basierend auf aktuellem Verbrauch
        current_weight = material.total_remaining_weight
        forecast = None
        if avg_consumption_per_day > 0 and current_weight > 0:
            days_remaining = current_weight / avg_consumption_per_day
            forecast = {
                'days_remaining': round(days_remaining, 1),
                'weeks_remaining': round(days_remaining / 7, 1),
                'estimated_depletion_date': (datetime.utcnow() + timedelta(days=days_remaining)).strftime('%d.%m.%Y')
            }
        
        # Empfehlungen generieren
        recommendations = []
        
        if current_weight <= (material.reorder_level_g or 0):
            recommendations.append({
                'type': 'critical',
                'message': 'Sofort nachbestellen! Bestand ist unter Mindestlevel.',
                'action': 'order_now'
            })
        elif forecast and forecast['days_remaining'] < 14:
            recommendations.append({
                'type': 'warning',
                'message': f'Nachbestellung empfohlen. Bestand reicht nur noch ca. {forecast["days_remaining"]} Tage.',
                'action': 'plan_order'
            })
        
        if available_spools == 0 and in_use_spools == 0:
            recommendations.append({
                'type': 'info',
                'message': 'Keine verfügbaren Spulen. Neue Spulen hinzufügen oder bestehende auffüllen.',
                'action': 'add_spools'
            })
        
        if not locations_list:
            recommendations.append({
                'type': 'info',
                'message': 'Spulen haben keinen zugewiesenen Lagerort.',
                'action': 'assign_location'
            })
        
        response_data = {
            'status': 'success',
            'material': {
                'id': material.id,
                'name': material.name,
                'manufacturer': material.manufacturer,
                'material_type': material.material_type,
                'color_hex': material.color_hex,
                'cost_per_spool': material.cost_per_spool,
                'spool_weight_g': material.spool_weight_g,
                'reorder_level_g': material.reorder_level_g
            },
            'inventory': {
                'total_weight_g': current_weight,
                'total_spools': total_spools,
                'available_spools': available_spools,
                'in_use_spools': in_use_spools,
                'empty_spools': empty_spools,
                'storage_locations': locations_list,
                'active_jobs': active_jobs
            },
            'consumption': {
                'last_usage_date': last_usage_date.strftime('%d.%m.%Y %H:%M') if last_usage_date else 'Nie verwendet',
                'avg_consumption_per_day_g': round(avg_consumption_per_day, 2),
                'total_consumption_30d_g': round(total_consumption_30d, 2),
                'total_consumption_all_time_g': round(total_consumption_all_time, 2),
                'total_jobs_completed': total_jobs_count,
                'avg_consumption_per_job_g': round(total_consumption_all_time / total_jobs_count, 2) if total_jobs_count > 0 else 0
            },
            'forecast': forecast,
            'recommendations': recommendations
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@filament_api_bp.route('/forecast')
@login_required
def get_consumption_forecast():
    """Gibt erweiterte Verbrauchsprognosen zurück"""
    filament_types = FilamentType.query.all()
    forecasts = []
    
    for ftype in filament_types:
        total_weight = ftype.total_remaining_weight
        
        if total_weight <= 0:
            continue
        
        # Echte Verbrauchsberechnung basierend auf Job-Historie
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_jobs = Job.query\
            .join(GCodeFile)\
            .filter(
                Job.required_filament_type_id == ftype.id,
                Job.status == JobStatus.COMPLETED,
                Job.completed_at >= thirty_days_ago
            ).all()
        
        total_consumption_30d = sum(job.gcode_file.material_needed_g or 0 for job in recent_jobs)
        avg_consumption_per_day = total_consumption_30d / 30 if total_consumption_30d > 0 else 0
        
        # Status bestimmen
        if ftype.reorder_level_g:
            if total_weight <= ftype.reorder_level_g * 0.5:
                status = 'critical'
            elif total_weight <= ftype.reorder_level_g:
                status = 'warning'
            else:
                status = 'ok'
        else:
            # Fallback ohne Reorder-Level
            if avg_consumption_per_day > 0:
                days_remaining = total_weight / avg_consumption_per_day
                if days_remaining < 7:
                    status = 'critical'
                elif days_remaining < 14:
                    status = 'warning'
                else:
                    status = 'ok'
            else:
                status = 'unknown'
        
        # Prognose berechnen
        if avg_consumption_per_day > 0:
            days_remaining = total_weight / avg_consumption_per_day
        else:
            # Fallback mit durchschnittlichem Verbrauch aller Materialien
            all_consumption = db.session.query(func.sum(GCodeFile.material_needed_g))\
                .join(Job)\
                .filter(
                    Job.status == JobStatus.COMPLETED,
                    Job.completed_at >= thirty_days_ago
                ).scalar() or 0
            
            all_material_count = FilamentType.query.count()
            fallback_daily_consumption = (all_consumption / 30 / all_material_count) if all_material_count > 0 else 25
            days_remaining = total_weight / fallback_daily_consumption
        
        forecasts.append({
            'material': f"{ftype.manufacturer} {ftype.name}",
            'color': ftype.color_hex,
            'total_weight_g': total_weight,
            'avg_consumption_per_day_g': round(avg_consumption_per_day, 2),
            'forecast': {
                'days_remaining': round(days_remaining, 1),
                'weeks_remaining': round(days_remaining / 7, 1),
                'note': 'Basierend auf Verbrauch der letzten 30 Tage' if avg_consumption_per_day > 0 else 'Geschätzt (keine Verbrauchsdaten)'
            },
            'status': status,
            'reorder_level': ftype.reorder_level_g,
            'recent_jobs_count': len(recent_jobs)
        })
    
    return jsonify({
        'status': 'success',
        'forecasts': forecasts
    })

@filament_api_bp.route('/qr-code/<int:spool_id>')
@login_required
def generate_qr_code(spool_id):
    """Generiert QR-Code für eine Spule"""
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool:
        return jsonify({'status': 'error', 'message': 'Spule nicht gefunden'}), 404
    
    try:
        qr_data = spool.generate_qr_code_data()
        qr_json = json.dumps(qr_data)
        
        # QR-Code Bild generieren
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_json)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # In Base64 konvertieren
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return jsonify({
            'status': 'success',
            'qr_code_data': qr_data,
            'qr_code_image': f"data:image/png;base64,{img_base64}"
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@filament_api_bp.route('/update-weight', methods=['POST'])
@login_required
def update_spool_weight():
    """Aktualisiert das Gewicht einer Spule"""
    data = request.get_json()
    
    spool_id = data.get('spool_id')
    new_weight = data.get('weight_g')
    notes = data.get('notes', '')
    
    if not all([spool_id, new_weight is not None]):
        return jsonify({'status': 'error', 'message': 'Fehlende Parameter'}), 400
    
    spool = db.session.get(FilamentSpool, spool_id)
    if not spool:
        return jsonify({'status': 'error', 'message': 'Spule nicht gefunden'}), 404
    
    try:
        old_weight = spool.current_weight_g
        spool.current_weight_g = float(new_weight)
        
        # Weight measurement history aktualisieren
        if spool.weight_measurements:
            measurements = spool.weight_measurements if isinstance(spool.weight_measurements, list) else []
        else:
            measurements = []
        
        measurements.append({
            'timestamp': datetime.utcnow().isoformat(),
            'weight_g': float(new_weight),
            'user_id': current_user.id,
            'notes': notes
        })
        
        # Nur die letzten 10 Messungen behalten
        spool.weight_measurements = measurements[-10:]
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Gewicht für {spool.short_id} aktualisiert',
            'old_weight': old_weight,
            'new_weight': new_weight,
            'remaining_percentage': spool.remaining_percentage
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@filament_api_bp.route('/available-spools/<int:printer_id>')
@login_required
def get_available_spools(printer_id):
    """Liefert verfügbare Spulen für einen bestimmten Drucker"""
    printer = db.session.get(Printer, printer_id)
    if not printer:
        return jsonify({'status': 'error', 'message': 'Drucker nicht gefunden'}), 404
    
    # Verfügbare Spulen (nicht in Benutzung, Gewicht > 0)
    available_spools = FilamentSpool.query\
        .join(FilamentType)\
        .filter(
            FilamentSpool.is_in_use == False,
            FilamentSpool.current_weight_g > 0
        )\
        .order_by(FilamentType.manufacturer, FilamentType.name)\
        .all()
    
    # Aktuelle Spule des Druckers
    current_spool = FilamentSpool.query.filter_by(
        assigned_to_printer_id=printer_id,
        is_in_use=True
    ).first()
    
    spools_data = []
    for spool in available_spools:
        spools_data.append({
            'id': spool.id,
            'short_id': spool.short_id,
            'material_name': f"{spool.filament_type.manufacturer} {spool.filament_type.name}",
            'material_type': spool.filament_type.material_type,
            'color_hex': spool.filament_type.color_hex,
            'current_weight_g': spool.current_weight_g,
            'remaining_percentage': spool.remaining_percentage,
            'storage_location': spool.storage_location or 'Unbekannt'
        })
    
    current_spool_data = None
    if current_spool:
        current_spool_data = {
            'id': current_spool.id,
            'short_id': current_spool.short_id,
            'material_name': f"{current_spool.filament_type.manufacturer} {current_spool.filament_type.name}",
            'color_hex': current_spool.filament_type.color_hex,
            'current_weight_g': current_spool.current_weight_g,
            'remaining_percentage': current_spool.remaining_percentage
        }
    
    return jsonify({
        'status': 'success',
        'printer_name': printer.name,
        'current_spool': current_spool_data,
        'available_spools': spools_data,
        'total_available': len(spools_data)
    })

@filament_api_bp.route('/assign-spool', methods=['POST'])
@login_required
def assign_spool_to_printer():
    """Weist eine Spule einem Drucker zu"""
    data = request.get_json()
    
    printer_id = data.get('printer_id')
    spool_id = data.get('spool_id')
    
    if not all([printer_id, spool_id]):
        return jsonify({'status': 'error', 'message': 'Drucker-ID und Spulen-ID erforderlich'}), 400
    
    printer = db.session.get(Printer, printer_id)
    spool = db.session.get(FilamentSpool, spool_id)
    
    if not printer:
        return jsonify({'status': 'error', 'message': 'Drucker nicht gefunden'}), 404
    if not spool:
        return jsonify({'status': 'error', 'message': 'Spule nicht gefunden'}), 404
    
    try:
        # Alte Spule vom Drucker entfernen
        old_spool = FilamentSpool.query.filter_by(
            assigned_to_printer_id=printer_id,
            is_in_use=True
        ).first()
        
        if old_spool:
            old_spool.is_in_use = False
            old_spool.assigned_to_printer_id = None
        
        # Neue Spule zuweisen
        spool.assigned_to_printer_id = printer_id
        spool.is_in_use = True
        spool.is_drying = False  # Spule ist nicht mehr im Trockner
        spool.last_used_date = date.today()
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Spule {spool.short_id} wurde Drucker {printer.name} zugewiesen',
            'old_spool_id': old_spool.id if old_spool else None,
            'new_spool_id': spool.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500