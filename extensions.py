from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from sqlalchemy import MetaData
from flask_wtf.csrf import CSRFProtect

# NEU: Konvention für Constraint-Namen, um Migrationsfehler mit SQLite zu beheben
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)

# Deklariert alle zentralen Erweiterungen
# Die "db"-Instanz wird jetzt mit der Namenskonvention initialisiert
db = SQLAlchemy(metadata=metadata)
login_manager = LoginManager()
socketio = SocketIO()
csrf = CSRFProtect()

