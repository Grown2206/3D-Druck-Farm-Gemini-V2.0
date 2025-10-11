# /models.py
import datetime
import enum
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db
import uuid
from sqlalchemy.types import TypeDecorator, VARCHAR
from sqlalchemy.dialects.sqlite import JSON
import json
from sqlalchemy import func
from extensions import db
from sqlalchemy import CheckConstraint, UniqueConstraint


# Association Table for SlicerProfile <-> Printer
slicer_profile_printers = db.Table('slicer_profile_printers',
    db.Column('slicer_profile_id', db.Integer, db.ForeignKey('slicer_profile.id'), primary_key=True),
    db.Column('printer_id', db.Integer, db.ForeignKey('printer.id'), primary_key=True)
)

# Association Table for SlicerProfile <-> FilamentType
slicer_profile_filaments = db.Table('slicer_profile_filaments',
    db.Column('slicer_profile_id', db.Integer, db.ForeignKey('slicer_profile.id'), primary_key=True),
    db.Column('filament_type_id', db.Integer, db.ForeignKey('filament_type.id'), primary_key=True)
)

# Association Table for Consumable <-> Printer
consumable_printers = db.Table('consumable_printers',
    db.Column('consumable_id', db.Integer, db.ForeignKey('consumable.id'), primary_key=True),
    db.Column('printer_id', db.Integer, db.ForeignKey('printer.id'), primary_key=True)
)


class RobustEnum(TypeDecorator):
    impl = VARCHAR
    cache_ok = True

    def __init__(self, enum_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enum_class = enum_class

    def process_bind_param(self, value, dialect):
        if isinstance(value, self._enum_class):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        if value is None: return None
        value_lower = str(value).lower()
        for member in self._enum_class:
            if member.value.lower() == value_lower or member.name.lower() == value_lower:
                return member
        if self._enum_class is CameraSource and str(value).upper() == 'NONE':
            return CameraSource.NONE
        return None

# --- Enums ---
class UserRole(str, enum.Enum):
    ADMIN = 'Admin'
    OPERATOR = 'Operator'

class PrinterStatus(str, enum.Enum):
    IDLE = 'Idle'
    PRINTING = 'Printing'
    QUEUED = 'Queued'
    MAINTENANCE = 'Maintenance'
    OFFLINE = 'Offline'
    ERROR = 'Error'

class JobQuality(str, enum.Enum):
    NOT_REVIEWED = 'Nicht geprüft'
    SUCCESSFUL = 'Erfolgreich'
    FAILED = 'Fehlgeschlagen'

class JobStatus(str, enum.Enum):
    PENDING = 'Pending'
    ASSIGNED = 'Assigned'
    QUEUED = 'Queued'
    PRINTING = 'Printing'
    COMPLETED = 'Completed'
    FAILED = 'Failed'
    CANCELLED = 'Cancelled'
    BATCHED = 'Gebündelt'

class APIType(str, enum.Enum):
    NONE = 'Manuell'
    KLIPPER = 'Klipper (Moonraker)'
    OCTOPRINT = 'OctoPrint'

class CameraSource(str, enum.Enum):
    NONE = 'Keine'
    NETWORK_URL = 'Netzwerk URL'
    USB_STREAMER = 'USB-Kamera (via Streamer)'

class MaintenanceTaskType(str, enum.Enum):
    CHECKLIST = 'Checklisten-Wartung'
    GENERAL = 'Allgemeine Wartung'
    LUBRICATION = 'Schmierung'
    CALIBRATION = 'Kalibrierung'
    BELT_TENSION = 'Riemenspannung'
    NOZZLE_CHANGE = 'Düsenwechsel'
    COMPONENT_REPLACEMENT = 'Komponententausch'
    CLEANING = 'Reinigung'
    OTHER = 'Sonstiges'

class MaintenanceTaskCategory(str, enum.Enum):
    MECHANICS = 'Mechanik'
    ELECTRONICS = 'Elektronik'
    CALIBRATION = 'Kalibrierung'
    CLEANING = 'Reinigung'
    GENERAL = 'Allgemein'

class PrinterType(str, enum.Enum):
    FDM = 'FDM'
    SLA = 'SLA'
    SLS = 'SLS'
    OTHER = 'Andere'

class BedType(str, enum.Enum):
    GLASS = 'Glas'
    PEI_SMOOTH = 'PEI (Glatt)'
    PEI_TEXTURED = 'PEI (Texturiert)'
    MAGNETIC = 'Magnetisch (Flexplate)'
    GAROLITE = 'Garolith'
    OTHER = 'Andere'

class ToDoCategory(str, enum.Enum):
    GENERAL = 'Allgemein'
    MAINTENANCE = 'Wartung'
    IMPROVEMENT = 'Verbesserung'
    BUGFIX = 'Fehlerbehebung'
    FEATURE = 'Neues Feature'

class ToDoStatus(str, enum.Enum):
    OPEN = 'Offen'
    IN_PROGRESS = 'In Bearbeitung'
    DONE = 'Erledigt'
    ON_HOLD = 'Zurückgestellt'
    
class LayoutItemType(str, enum.Enum):
    PRINTER = 'Drucker'
    TABLE = 'Tisch'
    SHELF = 'Regal'
    OBJECT = 'Objekt'

class ConsumableCategory(str, enum.Enum):
    NOZZLE = 'Düsen'
    BUILDPLATE = 'Druckbett'
    BELT = 'Riemen'
    LUBRICANT = 'Schmiermittel'
    CLEANING = 'Reinigungsmittel'
    ADHESIVE = 'Haftmittel'
    TOOL = 'Werkzeug'
    SPARE_PART = 'Ersatzteil'
    ELECTRONIC = 'Elektronik'
    MECHANICAL = 'Mechanik'
    CONSUMABLE = 'Verbrauchsmaterial'
    OTHER = 'Sonstiges'

class HazardSymbol(str, enum.Enum):
    GHS01_EXPLOSIVE = 'GHS01 - Explosiv'
    GHS02_FLAMMABLE = 'GHS02 - Entzündbar'
    GHS03_OXIDIZING = 'GHS03 - Oxidierend'
    GHS04_COMPRESSED_GAS = 'GHS04 - Gase unter Druck'
    GHS05_CORROSIVE = 'GHS05 - Ätzend'
    GHS06_TOXIC = 'GHS06 - Giftig'
    GHS07_HARMFUL = 'GHS07 - Gesundheitsschädlich'
    GHS08_HEALTH_HAZARD = 'GHS08 - Gesundheitsgefahr'
    GHS09_ENVIRONMENTAL = 'GHS09 - Umweltgefährlich'

class DeadlineStatus(str, enum.Enum):
    """Status-Codierung für Deadlines"""
    GREEN = 'green'      # > 72h verbleibend
    YELLOW = 'yellow'    # 24-72h verbleibend  
    RED = 'red'          # < 24h verbleibend
    OVERDUE = 'overdue'  # Deadline überschritten


class DependencyType(str, enum.Enum):
    """Typen von Job-Abhängigkeiten"""
    FINISH_TO_START = 'finish_to_start'  # Standard: B startet nachdem A endet
    START_TO_START = 'start_to_start'    # B startet wenn A startet
# --- Models ---

class SlicerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    slicer_args = db.Column(db.Text, nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    filename = db.Column(db.String(255), nullable=True)
    gcode_files = db.relationship('GCodeFile', backref='slicer_profile', lazy='dynamic')
    printers = db.relationship('Printer', secondary=slicer_profile_printers, back_populates='slicer_profiles', lazy='dynamic')
    compatible_filaments = db.relationship('FilamentType', secondary=slicer_profile_filaments, back_populates='slicer_profiles', lazy='dynamic')


class GCodeFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    source_stl_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    estimated_print_time_min = db.Column(db.Integer, nullable=True)
    material_needed_g = db.Column(db.Float, nullable=True)
    filament_needed_mm = db.Column(db.Float, nullable=True)
    tool_changes = db.Column(db.Integer, nullable=True)
    preview_image_filename = db.Column(db.String(255), nullable=True)
    layer_count = db.Column(db.Integer, nullable=True)
    dimensions_x_mm = db.Column(db.Float, nullable=True)
    dimensions_y_mm = db.Column(db.Float, nullable=True)
    filament_per_tool = db.Column(db.Text, nullable=True)
    material_type = db.Column(db.String(50), nullable=True)
    layer_height_mm = db.Column(db.Float, nullable=True)
    slicer_profile_id = db.Column(db.Integer, db.ForeignKey('slicer_profile.id'), nullable=True)
    jobs = db.relationship('Job', backref='gcode_file', lazy='dynamic')
    cost_calculations = db.relationship('CostCalculation', backref='gcode_file', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def preview_image_url(self):
        if self.preview_image_filename:
            return f'uploads/gcode/{self.preview_image_filename}'
        return None

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(RobustEnum(UserRole), default=UserRole.OPERATOR, nullable=False)
    maintenance_logs = db.relationship('MaintenanceLog', back_populates='user', lazy='dynamic')
    created_todos = db.relationship('ToDo', foreign_keys='ToDo.created_by_id', back_populates='creator', lazy='dynamic')
    assigned_todos = db.relationship('ToDo', foreign_keys='ToDo.assigned_to_id', back_populates='assignee', lazy='dynamic')

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Printer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    model = db.Column(db.String(120))
    status = db.Column(RobustEnum(PrinterStatus), default=PrinterStatus.IDLE, nullable=False)
    printer_type = db.Column(RobustEnum(PrinterType), default=PrinterType.FDM, nullable=False)
    max_speed = db.Column(db.Integer, nullable=True)
    max_acceleration = db.Column(db.Integer, nullable=True)
    extruder_count = db.Column(db.Integer, default=1, nullable=False)
    heated_chamber = db.Column(db.Boolean, default=False)
    heated_chamber_temp = db.Column(db.Integer, nullable=True)
    bed_type = db.Column(RobustEnum(BedType), default=BedType.PEI_TEXTURED, nullable=False)
    purchase_cost = db.Column(db.Float, nullable=True)
    cost_per_hour = db.Column(db.Float, nullable=True)
    power_consumption_w = db.Column(db.Integer, nullable=True)
    energy_price_kwh = db.Column(db.Float, nullable=True)
    commissioning_date = db.Column(db.Date, nullable=True)
    useful_life_years = db.Column(db.Integer, nullable=True)
    salvage_value = db.Column(db.Float, nullable=True)
    annual_maintenance_cost = db.Column(db.Float, nullable=True)
    annual_operating_hours = db.Column(db.Integer, nullable=True)
    imputed_interest_rate = db.Column(db.Float, nullable=True)
    camera_source = db.Column(RobustEnum(CameraSource), default=CameraSource.NONE, nullable=False)
    webcam_url = db.Column(db.String(255), nullable=True) 
    compatible_material_types = db.Column(db.String(200), default='')
    image_url = db.Column(db.String(255), nullable=True)
    build_volume_l = db.Column(db.Float, nullable=True)
    build_volume_w = db.Column(db.Float, nullable=True)
    build_volume_h = db.Column(db.Float, nullable=True)
    has_enclosure = db.Column(db.Boolean, default=False)
    has_filter = db.Column(db.Boolean, default=False)
    has_camera = db.Column(db.Boolean, default=False)
    has_led = db.Column(db.Boolean, default=False)
    has_ace = db.Column(db.Boolean, default=False)
    max_nozzle_temp = db.Column(db.Integer, nullable=True)
    max_bed_temp = db.Column(db.Integer, nullable=True)
    
    historical_print_hours = db.Column(db.Float, default=0.0)
    historical_filament_used_g = db.Column(db.Float, default=0.0)
    historical_jobs_count = db.Column(db.Integer, default=0)
    
    location = db.Column(db.String(100), nullable=True)
    last_maintenance_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    api_key = db.Column(db.String(64), nullable=True)
    api_type = db.Column(RobustEnum(APIType), default=APIType.NONE, nullable=False)
    maintenance_interval_h = db.Column(db.Integer, nullable=True)
    last_maintenance_h = db.Column(db.Float, default=0.0)
    last_nozzle_change_h = db.Column(db.Float, default=0.0)
    last_belt_tension_date = db.Column(db.Date, nullable=True)
    maintenance_checklist_state = db.Column(JSON, nullable=True)
    z_offset = db.Column(db.Float, nullable=True)
    last_vibration_calibration_date = db.Column(db.Date, nullable=True)
    flow_rate_result = db.Column(db.Float, nullable=True)
    pressure_advance_result = db.Column(db.Float, nullable=True)
    max_volumetric_speed_result = db.Column(db.Float, nullable=True)
    vfa_optimal_speed = db.Column(db.Integer, nullable=True)
    flow_rate_settings = db.Column(JSON, nullable=True)
    pressure_advance_settings = db.Column(JSON, nullable=True)
    vfa_test_settings = db.Column(JSON, nullable=True)

    jobs = db.relationship('Job', back_populates='assigned_printer', foreign_keys='Job.printer_id', lazy='dynamic')
    status_logs = db.relationship('PrinterStatusLog', backref='printer', lazy='dynamic', cascade="all, delete-orphan")
    maintenance_logs = db.relationship('MaintenanceLog', backref='printer', lazy='dynamic', cascade="all, delete-orphan")
    slicer_profiles = db.relationship('SlicerProfile', secondary=slicer_profile_printers, back_populates='printers', lazy='dynamic')
    assigned_spools = db.relationship('FilamentSpool', backref='assigned_printer', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def total_print_hours(self):
        new_seconds = db.session.query(func.sum(Job.actual_print_duration_s)).filter(Job.printer_id == self.id, Job.status == JobStatus.COMPLETED).scalar() or 0
        new_hours = new_seconds / 3600
        return round((self.historical_print_hours or 0) + new_hours, 1)

    @property
    def total_filament_used_g(self):
        new_grams = db.session.query(func.sum(GCodeFile.material_needed_g)).join(Job).filter(Job.printer_id == self.id, Job.status == JobStatus.COMPLETED).scalar() or 0
        return round((self.historical_filament_used_g or 0) + (new_grams or 0), 2)
    
    @property
    def total_jobs_count(self):
        new_jobs_count = self.jobs.filter(Job.status == JobStatus.COMPLETED).count()
        return (self.historical_jobs_count or 0) + new_jobs_count

    @property
    def calculated_cost_per_hour(self):
        cost = self.purchase_cost or 0
        salvage = self.salvage_value or 0
        life_years = self.useful_life_years or 0
        maintenance = self.annual_maintenance_cost or 0
        op_hours = self.annual_operating_hours or 0
        interest_rate = self.imputed_interest_rate or 0
        if not all([cost > 0, life_years > 0, op_hours > 0]):
            return None
        depreciation_per_year = (cost - salvage) / life_years
        avg_capital = (cost + salvage) / 2
        interest_per_year = avg_capital * (interest_rate / 100)
        total_annual_cost = depreciation_per_year + interest_per_year + maintenance
        cost_per_hour = total_annual_cost / op_hours
        return round(cost_per_hour, 2)

    def get_current_job(self): return self.jobs.filter(Job.status == JobStatus.PRINTING).first()
    
    def get_active_or_next_job(self):
        printing_job = self.get_current_job()
        if printing_job:
            return printing_job
        next_job = self.jobs.filter(
            Job.status.in_([JobStatus.QUEUED, JobStatus.ASSIGNED])
        ).order_by(Job.priority.desc(), Job.created_at.asc()).first()
        return next_job

    def is_available_at(self, check_time=None):
        """Prüft ob Drucker zu einer bestimmten Zeit verfügbar ist (Zeitfenster-Check).Args:check_time: datetime-Objekt oder None (nutzt aktuelle Zeit)Returns: bool: True wenn verfügbar"""
        if check_time is None:
            check_time = datetime.datetime.utcnow()
        
        # Wenn keine Zeitfenster definiert sind, ist Drucker immer verfügbar
        if not self.time_windows:
            return True
        
        # Prüfe ob mindestens ein aktives Zeitfenster passt
        for window in self.time_windows:
            if window.is_within_window(check_time):
                return True
        
        return False
    
    def get_next_available_time(self):
        """Gibt nächste verfügbare Zeit zurück wenn aktuell außerhalb Zeitfenster"""
        now = datetime.datetime.utcnow()
        
        if self.is_available_at(now):
            return now
        
        # Suche nächstes Zeitfenster in den nächsten 7 Tagen
        for days_ahead in range(7):
            check_date = now + datetime.timedelta(days=days_ahead)
            
            for window in self.time_windows:
                if not window.is_active:
                    continue
                
                if check_date.weekday() == window.day_of_week:
                    # Konstruiere nächste Startzeit
                    next_start = check_date.replace(
                        hour=window.start_time.hour,
                        minute=window.start_time.minute,
                        second=0,
                        microsecond=0
                    )
                    
                    if next_start > now:
                        return next_start
        
        return None  # Keine Zeitfenster in nächsten 7 Tagen



class MaintenanceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    task_type = db.Column(RobustEnum(MaintenanceTaskType), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    user = db.relationship('User', back_populates='maintenance_logs')

class Job(db.Model):
    # ==================== BESTEHENDE FELDER ====================
    # (Lass alle bestehenden Felder wie sie sind!)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    status = db.Column(RobustEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    priority = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    actual_print_duration_s = db.Column(db.Integer, nullable=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=True)
    gcode_file_id = db.Column(db.Integer, db.ForeignKey('g_code_file.id'), nullable=True)
    quality_assessment = db.Column(RobustEnum(JobQuality), default=JobQuality.NOT_REVIEWED, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    source_stl_filename = db.Column(db.String(255), nullable=True)
    required_filament_type_id = db.Column(db.Integer, db.ForeignKey('filament_type.id'), nullable=True)
    actual_filament_used_g = db.Column(db.Float, nullable=True)
    actual_cost = db.Column(db.Float, nullable=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=True)
    gcode_file_id = db.Column(db.Integer, db.ForeignKey('g_code_file.id'), nullable=True)
    required_filament_type_id = db.Column(db.Integer, db.ForeignKey('filament_type.id'), nullable=True)
    
    # NEUE Felder
    deadline = db.Column(db.DateTime, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='SET NULL'), nullable=True)
    parent_job_id = db.Column(db.Integer, db.ForeignKey('job.id', ondelete='SET NULL'), nullable=True)
    priority_score = db.Column(db.Float, default=0.0, nullable=False)
    is_on_critical_path = db.Column(db.Boolean, default=False, nullable=False)
    estimated_start_time = db.Column(db.DateTime, nullable=True)
    estimated_end_time = db.Column(db.DateTime, nullable=True)
    
    # Relationships (KORRIGIERT!)
    assigned_printer = db.relationship('Printer', foreign_keys=[printer_id], back_populates='jobs')
    required_filament_type = db.relationship('FilamentType', foreign_keys=[required_filament_type_id])
    cost_calculations = db.relationship('CostCalculation', backref='job', lazy='dynamic', cascade="all, delete-orphan")
    
    # NEUE Relationships
    project = db.relationship('Project', back_populates='jobs')
    parent_job = db.relationship('Job', remote_side=[id], backref='sub_jobs')
    
    # ==================== NEUE PROPERTIES (HINZUFÜGEN!) ====================
    
    @property
    def deadline_status(self):
        """Berechnet Deadline-Status mit Farbcodierung"""
        if not self.deadline:
            return None
        
        now = datetime.datetime.utcnow()
        time_remaining = (self.deadline - now).total_seconds() / 3600
        
        if time_remaining < 0:
            return DeadlineStatus.OVERDUE
        elif time_remaining < 24:
            return DeadlineStatus.RED
        elif time_remaining < 72:
            return DeadlineStatus.YELLOW
        else:
            return DeadlineStatus.GREEN
    
    @property
    def hours_until_deadline(self):
        """Gibt Stunden bis Deadline zurück"""
        if not self.deadline:
            return None
        
        now = datetime.datetime.utcnow()
        return round((self.deadline - now).total_seconds() / 3600, 1)
    
    @property
    def can_start(self):
        """Prüft ob alle Abhängigkeiten erfüllt sind"""
        for dep in self.dependencies:
            if dep.dependency_type == DependencyType.FINISH_TO_START:
                if dep.depends_on.status != JobStatus.COMPLETED:
                    return False
            elif dep.dependency_type == DependencyType.START_TO_START:
                if dep.depends_on.status == JobStatus.PENDING:
                    return False
        return True
    
    def get_blocking_dependencies(self):
        """Gibt Liste der blockierenden Abhängigkeiten zurück"""
        blocking = []
        for dep in self.dependencies:
            if dep.dependency_type == DependencyType.FINISH_TO_START:
                if dep.depends_on.status != JobStatus.COMPLETED:
                    blocking.append(dep)
            elif dep.dependency_type == DependencyType.START_TO_START:
                if dep.depends_on.status == JobStatus.PENDING:
                    blocking.append(dep)
        return blocking
    
    def get_all_dependencies(self, visited=None):
        """Gibt alle transitiven Abhängigkeiten zurück"""
        if visited is None:
            visited = set()
        
        if self.id in visited:
            return []
        
        visited.add(self.id)
        deps = [self]
        
        for dep in self.dependencies:
            deps.extend(dep.depends_on.get_all_dependencies(visited))
        
        return deps
    
    def get_elapsed_and_total_time_seconds(self):
        total_seconds = 0
        if self.gcode_file and self.gcode_file.estimated_print_time_min:
            total_seconds = self.gcode_file.estimated_print_time_min * 60
        elapsed_seconds = 0
        if self.status == JobStatus.PRINTING and self.start_time:
            elapsed_seconds = (datetime.datetime.utcnow() - self.start_time).total_seconds()
        return {'elapsed': elapsed_seconds, 'total': total_seconds}

    def get_manual_progress(self):
        time_data = self.get_elapsed_and_total_time_seconds()
        elapsed = time_data['elapsed']
        total = time_data['total']
        if total > 0:
            progress = (elapsed / total) * 100
            return min(100, progress)
        return 0

class PrintSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_failure = db.Column(db.Boolean, default=False, nullable=False)

class FilamentType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manufacturer = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    material_type = db.Column(db.String(30), nullable=False)
    color_hex = db.Column(db.String(7), nullable=False, default='#FFFFFF')
    density_gcm3 = db.Column(db.Float, default=1.24)
    diameter_mm = db.Column(db.Float, default=1.75)
    cost_per_spool = db.Column(db.Float)
    spool_weight_g = db.Column(db.Integer, default=1000)
    reorder_level_g = db.Column(db.Integer)
    currency = db.Column(db.String(10), default='EUR')
    datasheet_url = db.Column(db.String(255))
    print_settings = db.Column(db.Text)
    notes = db.Column(db.Text)
    spools = db.relationship('FilamentSpool', backref='filament_type', lazy='dynamic', cascade="all, delete-orphan")
    slicer_profiles = db.relationship('SlicerProfile', secondary=slicer_profile_filaments, back_populates='compatible_filaments', lazy='dynamic')
    
    __table_args__ = (db.UniqueConstraint('manufacturer', 'name', 'material_type', name='_manufacturer_name_type_uc'),)

    def get_print_settings(self):
        if not self.print_settings: return {}
        try: return json.loads(self.print_settings)
        except json.JSONDecodeError: return {}
        
    @property
    def total_spool_count(self):
        return self.spools.count()

    @property
    def available_spool_count(self):
        return self.spools.filter(FilamentSpool.is_in_use == False, FilamentSpool.current_weight_g > 0).count()

    @property
    def total_remaining_weight(self):
        total_weight = db.session.query(func.sum(FilamentSpool.current_weight_g)).filter(FilamentSpool.filament_type_id == self.id).scalar()
        return total_weight or 0

    def is_color_light(self):
        hex_color = self.color_hex.lstrip('#')
        if len(hex_color) != 6: return False
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance > 0.5
    
    def get_storage_requirements(self):
        """Gibt Lageranforderungen als Dict zurück"""
        return {
            'temperature_min': self.storage_temperature_min,
            'temperature_max': self.storage_temperature_max,
            'humidity_max': self.storage_humidity_max,
            'shelf_life_months': self.shelf_life_months
        }

    def get_drying_requirements(self):
        """Gibt Trocknungsparameter zurück"""
        return {
            'temperature': self.drying_temperature or 50,
            'duration_hours': self.drying_duration_hours or 6
        }

    def calculate_consumption_forecast(self, current_weight_g):
        """Berechnet Verbrauchsprognose basierend auf historischem Durchschnitt"""
        if not self.avg_consumption_g_per_hour or current_weight_g <= 0:
            return None
        
        # Aktuelle Druckaktivitäten berücksichtigen
        active_jobs = Job.query.filter(
            Job.status.in_([JobStatus.PRINTING, JobStatus.QUEUED]),
            Job.required_filament_type_id == self.id
        ).count()
        
        if active_jobs == 0:
            return {"days_remaining": "∞", "note": "Keine aktiven Drucke"}
        
        hours_remaining = current_weight_g / (self.avg_consumption_g_per_hour * active_jobs)
        days_remaining = hours_remaining / 24
        
        return {
            "days_remaining": round(days_remaining, 1),
            "hours_remaining": round(hours_remaining, 1),
            "active_jobs": active_jobs
        }


class FilamentSpool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filament_type_id = db.Column(db.Integer, db.ForeignKey('filament_type.id'), nullable=False)
    short_id = db.Column(db.String(4), unique=True, nullable=False)
    initial_weight_g = db.Column(db.Integer, default=1000)
    current_weight_g = db.Column(db.Integer, nullable=False)
    purchase_date = db.Column(db.Date)
    is_in_use = db.Column(db.Boolean, default=False, nullable=False)
    assigned_to_printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    notes = db.Column(db.Text)
    is_drying = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    drying_start_time = db.Column(db.DateTime, nullable=True)
    drying_temp = db.Column(db.Integer, nullable=True)
    drying_humidity = db.Column(db.Integer, nullable=True)
    
    # Neue Spalten aus Migration
    storage_location = db.Column(db.String(100), nullable=True)
    batch_number = db.Column(db.String(50), nullable=True)
    manufacturing_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    drying_end_time = db.Column(db.DateTime, nullable=True)
    drying_cycles_count = db.Column(db.Integer, nullable=True, server_default='0')
    last_used_date = db.Column(db.Date, nullable=True)
    qr_code = db.Column(db.String(50), nullable=True)
    weight_measurements = db.Column(JSON, nullable=True)
    usage_history = db.Column(JSON, nullable=True)
    
    def __init__(self, *args, **kwargs):
        super(FilamentSpool, self).__init__(*args, **kwargs)
        if not self.short_id:
            self.short_id = self.generate_short_id()

    @staticmethod
    def generate_short_id():
        while True:
            short_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            if not FilamentSpool.query.filter_by(short_id=short_id).first():
                return short_id

    @property
    def remaining_percentage(self):
        if self.current_weight_g is not None and self.initial_weight_g and self.initial_weight_g > 0:
            return max(0, min(100, round((self.current_weight_g / self.initial_weight_g) * 100)))
        return 0

    @property
    def is_expired(self):
        """Prüft ob die Spule abgelaufen ist"""
        if not self.expiry_date:
            return False
        return self.expiry_date < datetime.date.today()

    @property
    def is_expiring_soon(self):
        """Prüft ob die Spule bald abläuft (30 Tage)"""
        if not self.expiry_date:
            return False
        days_until_expiry = (self.expiry_date - datetime.date.today()).days
        return 0 < days_until_expiry <= 30

    @property
    def needs_drying(self):
        """Prüft ob die Spule getrocknet werden sollte"""
        if not self.last_used_date:
            return True
        days_since_use = (datetime.date.today() - self.last_used_date).days
        return days_since_use > 7

    @property
    def current_drying_session(self):
        """Temporär vereinfacht - gibt None zurück"""
        return None

    @property
    def is_currently_drying(self):
        """Prüft ob die Spule gerade getrocknet wird"""
        return self.is_drying


def start_drying_session(self, temperature, duration_hours, user_id, notes=None):
        """Startet eine neue Trocknungssession"""
        # Update Spool Status
        self.is_drying = True
        self.drying_start_time = datetime.datetime.utcnow()
        self.drying_temp = temperature
        self.drying_end_time = datetime.datetime.utcnow() + datetime.timedelta(hours=duration_hours)
        
        # Simuliere Session-Objekt
        class MockSession:
            def __init__(self, spool_id, temp, duration, user_id, notes):
                self.id = 1
                self.spool_id = spool_id
                self.temperature = temp
                self.duration_hours = duration
                self.user_id = user_id
                self.notes = notes
                self.start_time = datetime.datetime.utcnow()
                self.end_time = self.start_time + datetime.timedelta(hours=duration)
        
        return MockSession(self.id, temperature, duration_hours, user_id, notes)

def complete_drying_session(self):
        """Beendet die aktuelle Trocknungssession"""
        self.is_drying = False
        self.drying_start_time = None
        self.drying_temp = None
        self.drying_end_time = None
        self.drying_cycles_count = (self.drying_cycles_count or 0) + 1
        return True

def generate_qr_code_data(self):
        """Generiert QR-Code Daten für die Spule"""
        if not self.qr_code:
            self.qr_code = f"SPOOL-{self.short_id}-{self.id}"
        
        return {
            'type': 'filament_spool',
            'id': self.id,
            'short_id': self.short_id,
            'qr_code': self.qr_code,
            'material': f"{self.filament_type.manufacturer} {self.filament_type.name}",
            'color': self.filament_type.color_hex,
            'weight': self.current_weight_g
        }

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)

class Consumable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Basis-Informationen
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(RobustEnum(ConsumableCategory), default=ConsumableCategory.OTHER, nullable=False)
    description = db.Column(db.Text, nullable=True)
    usage_description = db.Column(db.Text, nullable=True)
    
    # Lagerbestand
    stock_level = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(20), default='Stück')
    min_stock = db.Column(db.Integer, nullable=True)
    reorder_level = db.Column(db.Integer, nullable=True)
    max_stock = db.Column(db.Integer, nullable=True)
    storage_location = db.Column(db.String(100), nullable=True)
    
    # Lieferanten-Informationen
    manufacturer = db.Column(db.String(100), nullable=True)
    supplier = db.Column(db.String(100), nullable=True)
    article_number = db.Column(db.String(50), nullable=True)
    ean = db.Column(db.String(13), nullable=True)
    
    # Preis-Informationen
    unit_price = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(10), default='EUR')
    last_ordered_date = db.Column(db.Date, nullable=True)
    last_order_quantity = db.Column(db.Integer, nullable=True)
    
    # Haltbarkeit
    has_expiry = db.Column(db.Boolean, default=False, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    
    # Medien
    image_filename = db.Column(db.String(255), nullable=True)
    datasheet_url = db.Column(db.String(255), nullable=True)
    
    # Sicherheit (JSON-Felder)
    hazard_symbols = db.Column(JSON, nullable=True)
    safety_warnings = db.Column(JSON, nullable=True)
    
    # Technische Daten
    specifications = db.Column(JSON, nullable=True)
    compatibility_tags = db.Column(db.String(255), nullable=True)
    
    # Metadaten
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Beziehungen
    compatible_printers = db.relationship('Printer', secondary=consumable_printers, backref=db.backref('consumables', lazy='dynamic'))
    
    @property
    def image_url(self):
        if self.image_filename:
            return f'uploads/consumables/{self.image_filename}'
        return None
    
    @property
    def is_low_stock(self):
        if self.reorder_level is not None:
            return self.stock_level <= self.reorder_level
        return False
    
    @property
    def is_critical_stock(self):
        if self.min_stock is not None:
            return self.stock_level < self.min_stock
        return False
    
    @property
    def is_expired(self):
        if self.has_expiry and self.expiry_date:
            return self.expiry_date < datetime.date.today()
        return False
    
    @property
    def is_expiring_soon(self):
        if self.has_expiry and self.expiry_date:
            days_until_expiry = (self.expiry_date - datetime.date.today()).days
            return 0 < days_until_expiry <= 30
        return False
    
    @property
    def stock_status(self):
        if self.is_critical_stock:
            return 'critical'
        elif self.is_low_stock:
            return 'low'
        elif self.max_stock and self.stock_level >= self.max_stock:
            return 'full'
        return 'normal'
    
    @property
    def total_value(self):
        if self.unit_price:
            return round(self.stock_level * self.unit_price, 2)
        return 0
    
    def get_hazard_symbols_list(self):
        if self.hazard_symbols:
            return self.hazard_symbols if isinstance(self.hazard_symbols, list) else []
        return []
    
    def get_safety_warnings_list(self):
        if self.safety_warnings:
            return self.safety_warnings if isinstance(self.safety_warnings, list) else []
        return []
    
    def get_specifications(self):
        if self.specifications:
            return self.specifications if isinstance(self.specifications, dict) else {}
        return {}
    
    def get_compatibility_tags_list(self):
        if self.compatibility_tags:
            return [tag.strip() for tag in self.compatibility_tags.split(',') if tag.strip()]
        return []
    
    def __repr__(self):
        return f'<Consumable {self.name}>'

class PrinterStatusLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=False)
    status = db.Column(RobustEnum(PrinterStatus), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class CostCalculation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    gcode_file_id = db.Column(db.Integer, db.ForeignKey('g_code_file.id'), nullable=False)
    filament_type_id = db.Column(db.Integer, db.ForeignKey('filament_type.id'), nullable=False)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=False)
    preparation_time_min = db.Column(db.Integer, default=0)
    post_processing_time_min = db.Column(db.Integer, default=0)
    employee_hourly_rate = db.Column(db.Float, default=0)
    margin_percent = db.Column(db.Float, default=0)
    material_cost = db.Column(db.Float)
    machine_cost = db.Column(db.Float)
    personnel_cost = db.Column(db.Float)
    total_cost_without_margin = db.Column(db.Float)
    total_price = db.Column(db.Float)
    filament_type = db.relationship('FilamentType')
    printer = db.relationship('Printer')
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)

class ToDo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(RobustEnum(ToDoCategory), default=ToDoCategory.GENERAL, nullable=False)
    status = db.Column(RobustEnum(ToDoStatus), default=ToDoStatus.OPEN, nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creator = db.relationship('User', foreign_keys=[created_by_id], back_populates='created_todos')
    assignee = db.relationship('User', foreign_keys=[assigned_to_id], back_populates='assigned_todos')

class MaintenanceTaskDefinition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(RobustEnum(MaintenanceTaskCategory), default=MaintenanceTaskCategory.GENERAL, nullable=False)
    interval_hours = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    instruction_url = db.Column(db.String(255), nullable=True)
    required_consumable_id = db.Column(db.Integer, db.ForeignKey('consumable.id'), nullable=True)
    required_consumable_quantity = db.Column(db.Integer, default=1)
    required_consumable = db.relationship('Consumable')
    
class LayoutItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    item_type = db.Column(db.Enum(LayoutItemType), nullable=False)
    model_path = db.Column(db.String(255), nullable=False)
    position_x = db.Column(db.Float, default=0.0)
    position_y = db.Column(db.Float, default=0.0)
    position_z = db.Column(db.Float, default=0.0)
    rotation_x = db.Column(db.Float, default=0.0)
    rotation_y = db.Column(db.Float, default=0.0)
    rotation_z = db.Column(db.Float, default=0.0)
    scale_x = db.Column(db.Float, default=1.0)
    scale_y = db.Column(db.Float, default=1.0)
    scale_z = db.Column(db.Float, default=1.0)
    is_visible = db.Column(db.Boolean, default=True, nullable=False, server_default='1')
    color = db.Column(db.String(7), nullable=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=True)
    printer = db.relationship('Printer', backref='layout_item', uselist=False)

    def __repr__(self):
        return f'<LayoutItem {self.name}>'

class Project(db.Model):
    """
    Gruppierung von zusammengehörigen Jobs (Multi-Part Jobs).
    Ermöglicht Projekt-Tracking und gemeinsame Deadlines.
    """
    __tablename__ = 'project'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    deadline = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)  # active, completed, cancelled
    color = db.Column(db.String(7), default='#0d6efd', nullable=False)  # Hex-Farbe für UI
    
    # Relationships
    jobs = db.relationship('Job', back_populates='project', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def completion_percentage(self):
        """Berechnet den Fortschritt des Projekts in Prozent"""
        total_jobs = self.jobs.count()
        if total_jobs == 0:
            return 0.0
        
        completed = self.jobs.filter_by(status=JobStatus.COMPLETED).count()
        return round((completed / total_jobs) * 100, 1)
    
    @property
    def deadline_status(self):
        """Berechnet den Deadline-Status des Projekts mit Farbcodierung"""
        if not self.deadline:
            return None
        
        now = datetime.datetime.utcnow()
        time_remaining = (self.deadline - now).total_seconds() / 3600  # in Stunden
        
        if time_remaining < 0:
            return DeadlineStatus.OVERDUE
        elif time_remaining < 24:
            return DeadlineStatus.RED
        elif time_remaining < 72:
            return DeadlineStatus.YELLOW
        else:
            return DeadlineStatus.GREEN
    
    @property
    def estimated_completion_time(self):
        """Berechnet voraussichtliche Fertigstellung basierend auf Jobs"""
        pending_jobs = self.jobs.filter(
            Job.status.in_([JobStatus.PENDING, JobStatus.ASSIGNED, JobStatus.QUEUED, JobStatus.PRINTING])
        ).all()
        
        if not pending_jobs:
            return datetime.datetime.utcnow()
        
        # Summiere geschätzte Zeiten
        total_minutes = 0
        for job in pending_jobs:
            if job.gcode_file and job.gcode_file.estimated_print_time_min:
                total_minutes += job.gcode_file.estimated_print_time_min
        
        return datetime.datetime.utcnow() + datetime.timedelta(minutes=total_minutes)
    
    def __repr__(self):
        return f'<Project {self.name}>'


class JobDependency(db.Model):
    """
    Definiert Abhängigkeiten zwischen Jobs.
    Job B kann erst starten wenn Job A bestimmte Bedingungen erfüllt.
    """
    __tablename__ = 'job_dependency'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id', ondelete='CASCADE'), nullable=False)
    depends_on_job_id = db.Column(db.Integer, db.ForeignKey('job.id', ondelete='CASCADE'), nullable=False)
    dependency_type = db.Column(
        RobustEnum(DependencyType), 
        default=DependencyType.FINISH_TO_START, 
        nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    job = db.relationship('Job', foreign_keys=[job_id], backref='dependencies')
    depends_on = db.relationship('Job', foreign_keys=[depends_on_job_id], backref='dependents')
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('job_id', 'depends_on_job_id', name='uq_job_dependency'),
        CheckConstraint('job_id != depends_on_job_id', name='ck_no_self_dependency'),
    )
    
    def __repr__(self):
        return f'<JobDependency Job{self.job_id} depends on Job{self.depends_on_job_id}>'


class TimeWindow(db.Model):
    """
    Definiert erlaubte Betriebszeiten für Drucker.
    Beispiel: Drucker läuft nur Montag-Freitag 8-18 Uhr.
    """
    __tablename__ = 'time_window'
    
    id = db.Column(db.Integer, primary_key=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Montag, 6=Sonntag
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)  # z.B. "Bürozeiten"
    
    # Relationship
    printer = db.relationship('Printer', backref='time_windows')
    
    __table_args__ = (
        CheckConstraint('day_of_week >= 0 AND day_of_week <= 6', name='ck_valid_weekday'),
    )
    
    def is_within_window(self, check_time=None):
        """
        Prüft ob eine bestimmte Zeit innerhalb des Zeitfensters liegt.
        
        Args:
            check_time: datetime-Objekt oder None (nutzt aktuelle Zeit)
            
        Returns:
            bool: True wenn innerhalb des Fensters
        """
        if check_time is None:
            check_time = datetime.datetime.utcnow()
        
        if not self.is_active:
            return False
        
        # Prüfe Wochentag
        if check_time.weekday() != self.day_of_week:
            return False
        
        # Prüfe Uhrzeit
        current_time = check_time.time()
        return self.start_time <= current_time <= self.end_time
    
    @property
    def weekday_name(self):
        """Gibt deutschen Wochentag zurück"""
        weekdays = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
        return weekdays[self.day_of_week]
    
    def __repr__(self):
        return f'<TimeWindow {self.weekday_name} {self.start_time}-{self.end_time}>'

    
# models.py - AM ENDE HINZUFÜGEN

class MaintenanceStatus(str, enum.Enum):
    SCHEDULED = 'Geplant'
    IN_PROGRESS = 'In Bearbeitung'
    COMPLETED = 'Abgeschlossen'
    OVERDUE = 'Überfällig'
    CANCELLED = 'Abgebrochen'

class MaintenancePriority(str, enum.Enum):
    LOW = 'Niedrig'
    MEDIUM = 'Mittel'
    HIGH = 'Hoch'
    CRITICAL = 'Kritisch'

class MaintenanceInterval(str, enum.Enum):
    HOURS = 'Druckstunden'
    DAYS = 'Tage'
    WEEKS = 'Wochen'
    MONTHS = 'Monate'
    MANUAL = 'Manuell'

task_printer_assignment = db.Table('task_printer_assignment',
    db.Column('task_id', db.Integer, db.ForeignKey('maintenance_task_new.id'), primary_key=True),
    db.Column('printer_id', db.Integer, db.ForeignKey('printer.id'), primary_key=True)
)

class MaintenanceTaskNew(db.Model):
    __tablename__ = 'maintenance_task_new'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(RobustEnum(MaintenanceTaskCategory), nullable=False)
    interval_type = db.Column(RobustEnum(MaintenanceInterval), default=MaintenanceInterval.MANUAL)
    interval_value = db.Column(db.Integer, nullable=True)
    priority = db.Column(RobustEnum(MaintenancePriority), default=MaintenancePriority.MEDIUM)
    estimated_duration_min = db.Column(db.Integer, nullable=True)
    checklist_items = db.Column(JSON, nullable=True)
    instruction_url = db.Column(db.String(255), nullable=True)
    instruction_pdf = db.Column(db.String(255), nullable=True)
    video_tutorial_url = db.Column(db.String(255), nullable=True)
    safety_warnings = db.Column(JSON, nullable=True)
    applicable_to_all = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    applicable_printers = db.relationship('Printer', secondary=task_printer_assignment, backref='assigned_maintenance_tasks')
    required_consumables = db.relationship('TaskConsumableNew', back_populates='task', cascade='all, delete-orphan')
    schedules = db.relationship('MaintenanceScheduleNew', back_populates='task', cascade='all, delete-orphan')
    executions = db.relationship('MaintenanceExecutionNew', back_populates='task')

class TaskConsumableNew(db.Model):
    __tablename__ = 'task_consumable_new'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('maintenance_task_new.id'), nullable=False)
    consumable_id = db.Column(db.Integer, db.ForeignKey('consumable.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    
    task = db.relationship('MaintenanceTaskNew', back_populates='required_consumables')
    consumable = db.relationship('Consumable')

class MaintenanceScheduleNew(db.Model):
    __tablename__ = 'maintenance_schedule_new'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('maintenance_task_new.id'), nullable=False)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=False)
    scheduled_date = db.Column(db.DateTime, nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(RobustEnum(MaintenanceStatus), default=MaintenanceStatus.SCHEDULED)
    priority = db.Column(RobustEnum(MaintenancePriority), nullable=True)
    triggered_by = db.Column(db.String(50), nullable=True)
    trigger_value = db.Column(db.Float, nullable=True)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    task = db.relationship('MaintenanceTaskNew', back_populates='schedules')
    printer = db.relationship('Printer')
    assigned_to = db.relationship('User')
    execution = db.relationship('MaintenanceExecutionNew', back_populates='schedule', uselist=False)

class MaintenanceExecutionNew(db.Model):
    __tablename__ = 'maintenance_execution_new'
    
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('maintenance_schedule_new.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('maintenance_task_new.id'), nullable=False)
    printer_id = db.Column(db.Integer, db.ForeignKey('printer.id'), nullable=False)
    performed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    actual_duration_min = db.Column(db.Integer, nullable=True)
    checklist_results = db.Column(JSON, nullable=True)
    issues_found = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    next_maintenance_recommended = db.Column(db.Date, nullable=True)
    labor_cost = db.Column(db.Float, nullable=True)
    parts_cost = db.Column(db.Float, nullable=True)
    total_cost = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    parts_ordered = db.Column(JSON, nullable=True)
    
    schedule = db.relationship('MaintenanceScheduleNew', back_populates='execution')
    task = db.relationship('MaintenanceTaskNew', back_populates='executions')
    printer = db.relationship('Printer')
    performed_by = db.relationship('User')
    photos = db.relationship('MaintenancePhotoNew', back_populates='execution', cascade='all, delete-orphan')
    used_consumables = db.relationship('ExecutionConsumableNew', back_populates='execution', cascade='all, delete-orphan')

class ExecutionConsumableNew(db.Model):
    __tablename__ = 'execution_consumable_new'
    
    id = db.Column(db.Integer, primary_key=True)
    execution_id = db.Column(db.Integer, db.ForeignKey('maintenance_execution_new.id'), nullable=False)
    consumable_id = db.Column(db.Integer, db.ForeignKey('consumable.id'), nullable=False)
    quantity_used = db.Column(db.Integer, default=1)
    
    execution = db.relationship('MaintenanceExecutionNew', back_populates='used_consumables')
    consumable = db.relationship('Consumable')

class MaintenancePhotoNew(db.Model):
    __tablename__ = 'maintenance_photo_new'
    
    id = db.Column(db.Integer, primary_key=True)
    execution_id = db.Column(db.Integer, db.ForeignKey('maintenance_execution_new.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    execution = db.relationship('MaintenanceExecutionNew', back_populates='photos')
    
    @property
    def url(self):
        return f'uploads/maintenance_photos/{self.filename}'
