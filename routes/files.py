# routes/files.py
from flask import Blueprint, send_from_directory, current_app, abort
from flask_login import login_required
import os

files_bp = Blueprint('files_bp', __name__)

@files_bp.route('/stl/<path:filename>')
@login_required
def serve_stl(filename):
    """Serves an STL file securely with the correct MIME type."""
    stl_folder = current_app.config.get('STL_FOLDER')
    
    # Wichtig: send_from_directory erwartet einen absoluten Pfad.
    # Wir stellen sicher, dass der Pfad absolut ist.
    if not os.path.isabs(stl_folder):
        stl_folder = os.path.join(current_app.root_path, stl_folder)

    if not stl_folder or not os.path.exists(stl_folder):
        abort(500, "STL storage path is not configured or does not exist.")
    
    return send_from_directory(
        directory=stl_folder,
        path=filename,
        mimetype='model/stl' # Dies ist der entscheidende Teil!
    )