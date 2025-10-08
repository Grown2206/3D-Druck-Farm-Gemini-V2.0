import os
from stl import mesh
import numpy as np

def get_stl_dimensions(file_path):
    """Liest eine STL-Datei und gibt ihre Bounding-Box-Dimensionen (Breite, Tiefe) zurück."""
    try:
        main_mesh = mesh.Mesh.from_file(file_path)
        # Bounding Box finden: minx, maxx, miny, maxy, minz, maxz
        min_vals = main_mesh.vectors.min(axis=(0, 1))
        max_vals = main_mesh.vectors.max(axis=(0, 1))
        
        width = max_vals[0] - min_vals[0]  # X-Achse
        depth = max_vals[1] - min_vals[1]  # Y-Achse
        return width, depth
    except Exception as e:
        print(f"Konnte STL-Dimensionen für {os.path.basename(file_path)} nicht lesen: {e}")
        return 0, 0

def arrange_stls_in_grid(stl_paths, bed_width, bed_depth, spacing=10):
    """
    Ordnet eine Liste von STL-Dateien in einem einfachen Raster an.
    Gibt eine Liste von Dictionaries mit Pfad und Position zurück.
    """
    parts = []
    for path in stl_paths:
        width, depth = get_stl_dimensions(path)
        if width > 0 and depth > 0:
            parts.append({'path': path, 'width': width, 'depth': depth, 'x': 0, 'y': 0})

    # Sortiert nach der größten Abmessung, um die Anordnung zu verbessern
    parts.sort(key=lambda p: max(p['width'], p['depth']), reverse=True)

    cursor_x, cursor_y = spacing, spacing
    row_height = 0
    positioned_parts = []

    for part in parts:
        part_width = part['width']
        part_depth = part['depth']

        # Wenn das Teil nicht in die aktuelle Zeile passt, zur nächsten Zeile springen
        if cursor_x + part_width > bed_width:
            cursor_x = spacing
            cursor_y += row_height + spacing
            row_height = 0

        # Wenn das Teil überhaupt nicht auf das Bett passt
        if part_width + spacing > bed_width or cursor_y + part_depth > bed_depth:
            print(f"Warnung: Teil {os.path.basename(part['path'])} passt nicht auf das Druckbett und wird übersprungen.")
            continue

        # Position berechnen (Mittelpunkt des Teils)
        part['x'] = cursor_x + (part_width / 2)
        part['y'] = cursor_y + (part_depth / 2)
        
        positioned_parts.append(part)
        
        # Cursor für das nächste Teil verschieben
        cursor_x += part_width + spacing
        # Die Höhe der aktuellen Zeile ist die Höhe des höchsten Teils in dieser Zeile
        row_height = max(row_height, part_depth)

    return positioned_parts