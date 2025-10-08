import re

def parse_gcode(file_path):
    """
    Liest eine G-Code-Datei und extrahiert die X-, Y- und Z-Koordinaten,
    gruppiert nach ihrem Typ (Perimeter, Infill, etc.) basierend auf Slicer-Kommentaren.
    """
    # Ein Dictionary, um die Pfade für jeden Typ zu speichern
    path_data = {
        "perimeter": [],
        "external_perimeter": [],
        "infill": [],
        "support": [],
        "skirt_brim": [],
        "travel": [], # Optional: für Bewegungen ohne Extrusion
        "unknown": []
    }
    
    last_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
    current_type = "unknown" # Standard-Typ

    # Regex, um Koordinaten effizient zu finden
    coord_re = re.compile(r'([XYZE])([\d\.-]+)')

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                
                # Prüfe auf Typ-Kommentare (PrusaSlicer, Cura etc.)
                if ';TYPE:' in line:
                    type_str = line.split(';TYPE:')[1].strip().lower()
                    if 'perimeter' in type_str:
                        current_type = "external_perimeter" if 'external' in type_str else "perimeter"
                    elif 'infill' in type_str:
                        current_type = "infill"
                    elif 'support' in type_str:
                        current_type = "support"
                    elif 'skirt' in line or 'brim' in line:
                        current_type = "skirt_brim"
                    else:
                        current_type = "unknown"
                    continue

                # Nur Bewegungsbefehle (G0/G1) berücksichtigen
                if line.startswith('G0') or line.startswith('G1'):
                    coords = dict(coord_re.findall(line.upper()))
                    
                    start_point = (last_pos['X'], last_pos['Y'], last_pos['Z'])

                    # Aktualisiere die letzte bekannte Position
                    if 'X' in coords: last_pos['X'] = float(coords['X'])
                    if 'Y' in coords: last_pos['Y'] = float(coords['Y'])
                    if 'Z' in coords: last_pos['Z'] = float(coords['Z'])
                    
                    end_point = (last_pos['X'], last_pos['Y'], last_pos['Z'])
                    
                    # Füge das Liniensegment dem aktuellen Typ hinzu
                    if start_point != end_point:
                        # Entscheide, ob extrudiert wird oder es eine reine Bewegung ist
                        is_extruding = 'E' in coords and float(coords['E']) > 0
                        
                        if is_extruding:
                            if current_type in path_data:
                                path_data[current_type].append([start_point, end_point])
                            else:
                                path_data["unknown"].append([start_point, end_point])
                        else:
                            # Reisebewegungen (ohne Extrusion) separat speichern
                            path_data["travel"].append([start_point, end_point])
                            
    except Exception as e:
        print(f"Fehler beim Parsen der G-Code-Datei {file_path}: {e}")
        # Im Fehlerfall leeres Dictionary zurückgeben
        return {}
        
    return path_data