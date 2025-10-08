🌟 Übersicht  


3D-Druck-Farm-Gemini-V2.0 ist eine webbasierte Anwendung, die entwickelt wurde, um den gesamten Workflow einer 3D-Druck-Farm zu verwalten. Von der Auftragsverwaltung über die Druckersteuerung und Materialverfolgung bis hin zur Kostenkalkulation und Leistungsanalyse bietet diese Software eine zentrale Plattform für Administratoren und Bediener.

Die Anwendung ermöglicht die nahtlose Integration mit Druckern über APIs (Klipper, OctoPrint), bietet ein detailliertes Dashboard zur Live-Überwachung und stellt Werkzeuge zur Verfügung, um die Effizienz und Produktivität der Farm zu maximieren.

✨ Haupt-Features


Dashboard & Live-Überwachung: 
Eine zentrale Ansicht des Status aller Drucker, laufender Aufträge, Materialbestände und anstehender Aufgaben.

Auftragsverwaltung (Jobs): Erstellen, Bearbeiten, Priorisieren und Zuweisen von Druckaufträgen. Inklusive CSV-Import und Archivierung abgeschlossener Aufträge.

Drucker-Management: Hinzufügen, Konfigurieren und Überwachen von beliebig vielen 3D-Druckern. Detaillierte Stammdatenverwaltung inklusive Wartungsprotokollen und Kalibrierungseinstellungen.

Material- & Spulenverwaltung: Verfolgung von Filament-Typen und einzelnen Spulen mit QR-Code-Unterstützung, Lagerbestands-Warnungen und einem Trocknungs-Manager.

Integrierter Slicer: Direkter Upload von STL-Dateien, Slicing mit vordefinierten Profilen (via PrusaSlicer CLI) und automatische G-Code-Analyse.

Batch-Planer: Effiziente Planung von Druckplatten durch Bündelung mehrerer Aufträge zu einem einzigen G-Code.

Kostenrechner: Detaillierte Kalkulation der Druckkosten basierend auf Material, Maschinenstunden und Personalkosten.

KPI-Dashboard: Umfassende Analyse der Farm-Leistung mit Kennzahlen zu Auslastung, Erfolgsquoten, Kosten und Materialverbrauch.

Digitaler Zwilling & Layout-Editor: Eine visuelle 3D-Repräsentation der Farm-Anordnung zur besseren Übersicht.

Wartungsplanung: Definition und Verwaltung von wiederkehrenden Wartungsaufgaben und Verbrauchsmaterialien.

Benutzerverwaltung: Rollenbasiertes System mit Administratoren und Bedienern.



🛠️ Verwendete Technologien


Backend: Python mit Flask

Datenbank: Flask-SQLAlchemy mit SQLite (erweiterbar)

Datenbank-Migrationen: Flask-Migrate (Alembic)

Benutzer-Authentifizierung: Flask-Login

Echtzeit-Kommunikation: Flask-SocketIO

Formulare: Flask-WTF

Frontend: HTML5, CSS3, JavaScript, Bootstrap, Chart.js

Hintergrund-Aufgaben: APScheduler

Slicing-Integration: PrusaSlicer (über CLI)

🚀 Setup & Installation


Folgen Sie diesen Schritten, um die Anwendung lokal auszuführen:

1. Voraussetzungen:

Python 3.8+

Git

(Optional, aber empfohlen) PrusaSlicer für die Slicing-Funktionalität.

2. Klonen des Repositories:

Bash

git clone https://github.com/grown2206/3d-druck-farm-gemini-v2.0.git
cd 3D-Druck-Farm-Gemini-V2.0-a3a2a0ff1f56b4cde7cf692faf86b20387be1f4e
3. Virtuelle Umgebung erstellen (empfohlen):

Bash

python -m venv venv
source venv/bin/activate  # Auf Windows: venv\Scripts\activate
4. Abhängigkeiten installieren:

Bash

pip install -r requirements.txt
5. Umgebungsvariablen konfigurieren:
Erstellen Sie eine Datei namens .env im Hauptverzeichnis des Projekts und fügen Sie die folgenden Variablen hinzu. Passen Sie die Pfade entsprechend Ihrer PrusaSlicer-Installation an.

Code-Snippet

# Ein geheimer Schlüssel für die Flask-Session-Sicherheit
SECRET_KEY='ein-sehr-geheimer-schluessel'

# Pfade zur PrusaSlicer CLI und dessen Datenverzeichnis
# Beispiel für Windows:
PRUSA_SLICER_PATH="C:\\Program Files\\Prusa3D\\PrusaSlicer\\prusa-slicer-console.exe"
PRUSA_SLICER_DATADIR="C:\\Users\\IhrBenutzer\\AppData\\Roaming\\PrusaSlicer"
6. Datenbank initialisieren:
Die Datenbank (database.db) wird beim ersten Start automatisch im instance-Ordner erstellt. Ein Standard-Admin-Benutzer wird ebenfalls angelegt.

7. Anwendung starten:

Bash

flask run
Alternativ kann die Anwendung direkt über app.py gestartet werden, um den Debug-Modus und den SocketIO-Server zu nutzen:

Bash

python app.py
Die Anwendung ist nun unter http://127.0.0.1:5000 erreichbar.

Standard-Login:

Benutzername: admin

Passwort: admin

📖 Benutzung


Nach dem ersten Login sollten Sie die folgenden Schritte durchführen, um die Farm einzurichten:

Drucker anlegen: Gehen Sie zum Menüpunkt "Drucker" und fügen Sie Ihre Drucker mit den entsprechenden Spezifikationen und API-Daten (falls vorhanden) hinzu.

Materialien definieren: Unter "Materialien" können Sie die von Ihnen verwendeten Filament-Typen anlegen und anschließend einzelne Spulen zum Inventar hinzufügen.

Slicer-Profile erstellen: Im Slicer-Bereich können Sie .ini-Konfigurationsdateien von PrusaSlicer hochladen und diese Druckern und Materialien zuweisen.

Aufträge erstellen: Erstellen Sie neue Druckaufträge, laden Sie die zugehörigen STL-Dateien hoch und weisen Sie diese den Druckern zu.

📂 Projektstruktur




/
├── instance/                 # Instanz-Ordner (enthält die DB)
├── migrations/               # Alembic-Migrationsskripte
├── routes/                   # Flask Blueprints für die verschiedenen Module
│   ├── api.py
│   ├── auth.py
│   └── ...
├── slicer_profiles/          # Speicherort für Slicer-Konfigurationsdateien
├── static/                   # Statische Dateien (CSS, JS, Bilder)
│   ├── uploads/              # Speicherort für hochgeladene Dateien (STL, G-Code etc.)
│   └── ...
├── templates/                # Jinja2-Templates
│   ├── jobs/
│   ├── printers/
│   └── ...
├── .env                      # Umgebungsvariablen (lokal)
├── app.py                    # Hauptanwendungsdatei (Flask App Factory)
├── models.py                 # SQLAlchemy-Datenbankmodelle
├── requirements.txt          # Python-Abhängigkeiten
└── ... 
