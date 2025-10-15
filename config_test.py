# config_test.py - NEUE DATEI ERSTELLEN
"""
Test-spezifische Konfiguration.
Diese Datei stellt sicher, dass Tests NIEMALS die Produktions-Datenbank verwenden.
"""
import os
import tempfile

class TestConfig:
    """Konfiguration für Tests."""
    
    TESTING = True
    
    # WICHTIG: Separate Test-Datenbank
    # Option 1: In-Memory (schnell, aber nicht persistent)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Option 2: Temporäre Datei (persistent während Test-Lauf)
    # SQLALCHEMY_DATABASE_URI = f'sqlite:///{tempfile.gettempdir()}/test_database.db'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # CSRF für Tests deaktivieren
    WTF_CSRF_ENABLED = False
    
    # Login für Tests erlauben
    LOGIN_DISABLED = False
    
    # Server-Name für url_for in Tests
    SERVER_NAME = 'localhost.test'
    
    # Secret Key für Tests
    SECRET_KEY = 'test-secret-key-for-testing-only-12345'
    
    # Upload-Ordner für Tests (temporär)
    UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'test_uploads')
    PRINTER_IMAGES_FOLDER = os.path.join(tempfile.gettempdir(), 'test_uploads', 'printer_images')
    STL_FOLDER = os.path.join(tempfile.gettempdir(), 'test_uploads', 'stl_files')
    GCODE_FOLDER = os.path.join(tempfile.gettempdir(), 'test_uploads', 'gcode')
    SLICER_PROFILES_FOLDER = os.path.join(tempfile.gettempdir(), 'slicer_profiles')
    SNAPSHOT_FOLDER = os.path.join(tempfile.gettempdir(), 'test_uploads', 'snapshots')
    
    @staticmethod
    def init_app(app):
        """Initialisiert die Test-Umgebung."""
        # Erstelle Test-Ordner
        import os
        for folder in [
            TestConfig.UPLOAD_FOLDER,
            TestConfig.PRINTER_IMAGES_FOLDER,
            TestConfig.STL_FOLDER,
            TestConfig.GCODE_FOLDER,
            TestConfig.SLICER_PROFILES_FOLDER,
            TestConfig.SNAPSHOT_FOLDER
        ]:
            os.makedirs(folder, exist_ok=True)