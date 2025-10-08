import sqlite3
import os

# Pfad zur Datenbankdatei
DB_PATH = os.path.join('instance', 'database.db')

def cleanup_model_paths():
    """
    Stellt eine Verbindung zur Datenbank her, findet und korrigiert
    fehlerhafte model_path-Einträge in der layout_item-Tabelle.
    """
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbankdatei nicht gefunden unter '{DB_PATH}'")
        return

    try:
        # Verbindung zur SQLite-Datenbank herstellen
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Alle Einträge aus der layout_item-Tabelle abrufen
        cursor.execute("SELECT id, model_path FROM layout_item")
        items = cursor.fetchall()

        items_to_update = []
        for item_id, model_path in items:
            if model_path and ('/' in model_path or '\\' in model_path):
                # Extrahiere nur den Dateinamen aus dem Pfad
                clean_filename = os.path.basename(model_path)
                if clean_filename != model_path:
                    items_to_update.append((clean_filename, item_id))

        if not items_to_update:
            print("Keine fehlerhaften Pfade in der Datenbank gefunden. Alles in Ordnung.")
            return

        print(f"Korrumpierte Pfade gefunden. Starte die Bereinigung für {len(items_to_update)} Einträge...")

        # Die fehlerhaften Einträge aktualisieren
        cursor.executemany("UPDATE layout_item SET model_path = ? WHERE id = ?", items_to_update)
        
        # Änderungen speichern
        conn.commit()
        
        print("Datenbank erfolgreich bereinigt!")
        for filename, item_id in items_to_update:
            print(f"  - ID {item_id}: Pfad korrigiert zu '{filename}'")

    except sqlite3.Error as e:
        print(f"Ein Datenbankfehler ist aufgetreten: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    cleanup_model_paths()