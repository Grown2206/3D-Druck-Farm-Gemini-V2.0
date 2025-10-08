# utils.py
import functools
from flask import flash, redirect, url_for
from flask_login import current_user
from models import UserRole

def requires_roles(*roles):
    """
    Ein Dekorator, um den Zugriff auf Routen auf bestimmte Benutzerrollen zu beschränken.
    """
    def wrapper(f):
        @functools.wraps(f)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth_bp.login'))
            
            # KORREKTUR: Vergleicht den WERT der Benutzerrolle (z.B. 'Admin') 
            # mit den erlaubten Rollen-Texten. Das behebt den Berechtigungsfehler.
            if not hasattr(current_user, 'role') or current_user.role.value not in roles:
                flash("Sie haben nicht die erforderlichen Berechtigungen, um auf diese Seite zuzugreifen.", "danger")
                return redirect(url_for('jobs_bp.dashboard')) # Leitet zum Dashboard um
            
            return f(*args, **kwargs)
        return decorated_view
    return wrapper