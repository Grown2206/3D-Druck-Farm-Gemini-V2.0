from flask import Flask

def register_blueprints(app: Flask):
    from .auth import auth_bp
    from .calculator import calculator_bp
    from .consumables import consumables_bp
    from .files import files_bp
    from .gantt import gantt_bp
    from .jobs import jobs_bp
    from .kpi import kpi_bp
    from .maintenance import maintenance_bp
    from .materials import materials_bp
    from .printers import printers_bp
    from .printer_actions import printer_actions_bp
    from .slicer import slicer_bp  # <-- WIEDER AKTIVIERT
    from .slicer_profiles import slicer_profiles_bp
    from .todo import todo_bp
    from .api import api_bp
    from .visualizer import visualizer_bp
    from .digital_twin import digital_twin_bp
    from .layout_editor import layout_editor_bp
    from .batch_planner import batch_planner_bp
    from .maintenance_new import maintenance_new_bp
    from .filament_api import filament_api_bp



    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(calculator_bp, url_prefix='/calculator')
    app.register_blueprint(consumables_bp, url_prefix='/consumables')
    app.register_blueprint(files_bp, url_prefix='/files')
    app.register_blueprint(gantt_bp, url_prefix='/gantt')
    app.register_blueprint(jobs_bp, url_prefix='/jobs')
    app.register_blueprint(kpi_bp, url_prefix='/kpi')
    app.register_blueprint(maintenance_bp, url_prefix='/maintenance')
    app.register_blueprint(materials_bp, url_prefix='/materials')
    app.register_blueprint(printers_bp, url_prefix='/printers')
    app.register_blueprint(printer_actions_bp, url_prefix='/printer_actions')
    app.register_blueprint(slicer_bp, url_prefix='/slicer') # <-- WIEDER AKTIVIERT
    app.register_blueprint(slicer_profiles_bp, url_prefix='/slicer-profiles')
    app.register_blueprint(todo_bp, url_prefix='/todo')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(visualizer_bp)
    app.register_blueprint(digital_twin_bp)
    app.register_blueprint(layout_editor_bp)
    app.register_blueprint(batch_planner_bp)
    app.register_blueprint(maintenance_new_bp)
    app.register_blueprint(filament_api_bp)
