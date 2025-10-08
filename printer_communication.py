# printer_communication.py
import requests
import os
from models import APIType, PrinterStatus, JobQuality # JobQuality importiert

def test_printer_connection(printer):
    """
    Testet die Netzwerkverbindung zu einem Drucker.
    """
    if not printer.ip_address:
        return False, "Keine IP-Adresse konfiguriert."
    try:
        if printer.api_type == APIType.OCTOPRINT:
            api_url = f"http://{printer.ip_address}/api/version"
        elif printer.api_type == APIType.KLIPPER:
            api_url = f"http://{printer.ip_address}/printer/info"
        else:
            return False, "Für manuelle Drucker kann keine Verbindung getestet werden."
        response = requests.get(api_url, timeout=3)
        response.raise_for_status()
        return True, f"Drucker unter {printer.ip_address} ist erreichbar."
    except requests.RequestException:
        return False, f"Verbindungsfehler: Drucker unter {printer.ip_address} nicht erreichbar."
    except Exception as e:
        return False, f"Ein unerwarteter Fehler ist aufgetreten: {e}"

def get_printer_status(printer):
    """
    Ruft den Status eines Druckers ab, inklusive Zuverlässigkeitsdaten.
    """
    active_job = printer.get_active_or_next_job()
    time_info = active_job.get_elapsed_and_total_time_seconds() if active_job else {'elapsed': 0, 'total': 0}

    # --- ZWEITE, FINALE KORREKTUR ---
    # Die Zählung der Jobs wird nun korrekt über die Datenbank-Relation durchgeführt.
    successful_jobs_count = printer.jobs.filter_by(quality_assessment=JobQuality.SUCCESSFUL).count()
    failed_jobs_count = printer.jobs.filter_by(quality_assessment=JobQuality.FAILED).count()
    
    status_dict = {
        'state': printer.status.value,
        'db_status': True,
        'progress': active_job.get_manual_progress() if active_job else 0,
        'job_name': active_job.name if active_job else None,
        'job_id': active_job.id if active_job else None,
        'preview_image_url': active_job.gcode_file.preview_image_url if active_job and active_job.gcode_file else None,
        'time_info': time_info,
        'temps': { 'nozzle_actual': 0, 'nozzle_target': 0, 'bed_actual': 0, 'bed_target': 0 },
        'reliability': { 'successful': successful_jobs_count, 'failed': failed_jobs_count }
    }

    if printer.api_type == APIType.NONE or not printer.ip_address:
        return status_dict

    try:
        api_data = {}
        if printer.api_type == APIType.KLIPPER:
            api_data = _get_klipper_status(printer)
        elif printer.api_type == APIType.OCTOPRINT:
            api_data = _get_octoprint_status(printer)
        
        if api_data:
            api_state = PrinterStatus(api_data.get('state', 'Offline'))
            db_state = printer.status
            if db_state == PrinterStatus.PRINTING and api_state == PrinterStatus.IDLE:
                api_data['progress'] = status_dict['progress']
                api_data['time_info'] = status_dict['time_info']
                api_data['state'] = PrinterStatus.PRINTING.value
            status_dict.update(api_data)
            status_dict['db_status'] = False
        
        if not status_dict.get('job_name') and active_job:
            status_dict['job_name'] = active_job.name
            status_dict['job_id'] = active_job.id
            status_dict['preview_image_url'] = active_job.gcode_file.preview_image_url if active_job.gcode_file else None
        
        return status_dict
    except requests.RequestException:
        status_dict['state'] = PrinterStatus.OFFLINE.value
        return status_dict

# ... (Rest der Datei: _get_klipper_status, _get_octoprint_status etc. bleiben unverändert)
def control_printer_job(printer, command):
    if printer.api_type == APIType.NONE or not printer.ip_address:
        return False, "Manuelle Drucker können nicht ferngesteuert werden."
    try:
        if printer.api_type == APIType.OCTOPRINT:
            return _send_octoprint_command(printer, command)
        elif printer.api_type == APIType.KLIPPER:
            return _send_klipper_command(printer, command)
        else:
            return False, "Unbekannter API-Typ für die Steuerung."
    except requests.RequestException as e:
        return False, f"Verbindungsfehler: {e}"
    except Exception as e:
        return False, f"Ein unerwarteter Fehler ist aufgetreten: {e}"

def _get_api_key(printer):
    if not printer.api_key:
        return None, "API-Schlüssel-Variable nicht in der DB konfiguriert."
    actual_api_key = os.getenv(printer.api_key)
    if not actual_api_key:
        return None, f'API-Schlüssel-Variable "{printer.api_key}" nicht in der .env-Datei gefunden.'
    return actual_api_key, None

def _send_octoprint_command(printer, command):
    api_key, error = _get_api_key(printer)
    if error: return False, error
    url = f"http://{printer.ip_address}/api/job"
    headers = {'X-Api-Key': api_key, 'Content-Type': 'application/json'}
    
    if command == 'pause':
        payload = {'command': 'pause', 'action': 'toggle'}
    elif command == 'resume':
         payload = {'command': 'pause', 'action': 'resume'}
    else: # cancel
        payload = {'command': command}

    response = requests.post(url, headers=headers, json=payload, timeout=5)

    if response.status_code == 204:
        return True, f"Befehl '{command}' erfolgreich an {printer.name} gesendet."
    else:
        return False, f"Fehler von OctoPrint: {response.status_code} - {response.text}"

def _send_klipper_command(printer, command):
    klipper_command_map = {'pause': 'pause', 'resume': 'resume', 'cancel': 'cancel'}
    endpoint = klipper_command_map.get(command)
    if not endpoint: return False, f"Unbekannter Klipper-Befehl: {command}"

    url = f"http://{printer.ip_address}/printer/print/{endpoint}"
    response = requests.post(url, timeout=5)
    if response.ok:
        return True, f"Befehl '{command}' erfolgreich an {printer.name} gesendet."
    else:
        error_msg = response.json().get('error', {}).get('message', response.text)
        return False, f"Fehler von Klipper/Moonraker: {response.status_code} - {error_msg}"


def _get_klipper_status(printer):
    url = f"http://{printer.ip_address}/printer/objects/query?print_stats&tool_heater&extruder&heater_bed"
    response = requests.get(url, timeout=2) 
    response.raise_for_status()
    data = response.json().get('result', {}).get('status', {})
    print_stats = data.get('print_stats', {})
    state_str = print_stats.get('state', 'unknown').upper()
    status_map = {
        'PRINTING': PrinterStatus.PRINTING.value, 'PAUSED': PrinterStatus.MAINTENANCE.value,
        'STANDBY': PrinterStatus.IDLE.value, 'COMPLETE': PrinterStatus.IDLE.value,
        'CANCELLED': PrinterStatus.IDLE.value, 'ERROR': PrinterStatus.ERROR.value, 
    }
    total_duration = print_stats.get('total_duration', 0)
    print_duration = print_stats.get('print_duration', 0)
    
    time_info = {'elapsed': print_duration, 'total': total_duration}

    return {
        'state': status_map.get(state_str, PrinterStatus.OFFLINE.value),
        'progress': round(print_stats.get('progress', 0) * 100, 1),
        'time_info': time_info,
        'job_name': print_stats.get('filename'),
        'temps': {
            'nozzle_actual': data.get('extruder', {}).get('temperature', 0),
            'nozzle_target': data.get('extruder', {}).get('target', 0),
            'bed_actual': data.get('heater_bed', {}).get('temperature', 0),
            'bed_target': data.get('heater_bed', {}).get('target', 0),
        }
    }

def _get_octoprint_status(printer):
    api_key, error = _get_api_key(printer)
    if error: return {'state': PrinterStatus.ERROR.value, 'error': error}
    base_url = f"http://{printer.ip_address}/api"
    headers = {'X-Api-Key': api_key}
    printer_response = requests.get(f"{base_url}/printer", headers=headers, timeout=2)
    printer_response.raise_for_status()
    printer_data = printer_response.json()
    job_response = requests.get(f"{base_url}/job", headers=headers, timeout=2)
    job_data = job_response.json() if job_response.ok else {}
    state_flags = printer_data.get('state', {}).get('flags', {})
    if state_flags.get('printing'): state = PrinterStatus.PRINTING.value
    elif state_flags.get('paused'): state = PrinterStatus.MAINTENANCE.value
    elif state_flags.get('operational'): state = PrinterStatus.IDLE.value
    elif state_flags.get('error'): state = PrinterStatus.ERROR.value
    else: state = PrinterStatus.OFFLINE.value
    
    progress_data = job_data.get('progress', {})
    elapsed = progress_data.get('printTime', 0)
    total = elapsed + progress_data.get('printTimeLeft', 0) if progress_data.get('printTimeLeft') is not None else 0
    time_info = {'elapsed': elapsed, 'total': total}

    return {
        'state': state,
        'progress': round(progress_data.get('completion', 0) or 0, 1),
        'time_info': time_info,
        'job_name': job_data.get('job', {}).get('file', {}).get('name'),
        'temps': {
            'nozzle_actual': printer_data.get('temperature', {}).get('tool0', {}).get('actual', 0),
            'nozzle_target': printer_data.get('temperature', {}).get('tool0', {}).get('target', 0),
            'bed_actual': printer_data.get('temperature', {}).get('bed', {}).get('actual', 0),
            'bed_target': printer_data.get('temperature', {}).get('bed', {}).get('target', 0),
        }
    }