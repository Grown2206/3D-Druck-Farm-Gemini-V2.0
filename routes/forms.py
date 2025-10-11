import enum
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, IntegerField, FloatField, BooleanField, DateField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError
from models import UserRole, MaintenanceTaskType
import inspect
from datetime import datetime
from models import User

class RegistrationForm(FlaskForm):
    """Formular für die Benutzerregistrierung."""
    username = StringField('Benutzername', 
                           validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Passwort', 
                             validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Passwort bestätigen', 
                                     validators=[DataRequired(), EqualTo('password', message='Passwörter müssen übereinstimmen.')])
    submit = SubmitField('Registrieren')

    def validate_username(self, username):
        """Prüft, ob der Benutzername bereits existiert."""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Dieser Benutzername ist bereits vergeben. Bitte wählen Sie einen anderen.')

class LoginForm(FlaskForm):
    """Formular für die Benutzeranmeldung."""
    username = StringField('Benutzername', 
                           validators=[DataRequired()])
    password = PasswordField('Passwort', 
                             validators=[DataRequired()])
    submit = SubmitField('Anmelden')
# --- Formular für den Slicer (KORRIGIERT) ---
class SlicerForm(FlaskForm):
    stl_file = FileField(
        'STL-Datei',
        validators=[
            FileRequired(message='Bitte wählen Sie eine Datei aus.'),
            FileAllowed(['stl'], 'Nur STL-Dateien sind erlaubt!')
        ]
    )
    # coerce=int wurde bei den folgenden zwei Feldern entfernt, um den ValueError zu beheben
    printer_id = SelectField('Drucker', validators=[Optional()])
    material_type = SelectField('Materialtyp', validators=[Optional()])
    slicer_profile_id = SelectField('Slicer-Profil', validators=[DataRequired(message='Bitte wählen Sie ein Profil aus.')])
    submit = SubmitField('Slicing-Prozess starten')


# --- Bestehende Formulare ---

class RegistrationForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Passwort', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Passwort bestätigen', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Rolle', choices=[(role.value, role.name) for role in UserRole], default=UserRole.OPERATOR.value, validators=[DataRequired()])
    submit = SubmitField('Registrieren')

class LoginForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired()])
    password = PasswordField('Passwort', validators=[DataRequired()])
    submit = SubmitField('Anmelden')

class MaintenanceLogForm(FlaskForm):
    """Formular zum Hinzufügen eines Wartungsprotokolls."""
    task_type = SelectField('Aufgabentyp',
                            choices=[(choice.value, choice.value) for choice in MaintenanceTaskType],
                            validators=[DataRequired(message="Bitte wählen Sie einen Aufgabentyp aus.")])
    notes = TextAreaField('Notizen',
                        validators=[Optional(), Length(max=5000)])
    submit = SubmitField('Protokoll hinzufügen')


# --- Wiederhergestellte Helper-Funktion ---
def update_model_from_form(model, form_data, field_mapping):
    """
    Befüllt ein SQLAlchemy-Modellobjekt dynamisch aus Formulardaten.
    """
    for form_field, (model_attr, field_type) in field_mapping.items():
        if form_field in form_data:
            value_str = form_data.get(form_field, '').strip()

            if field_type not in [str, bool] and value_str == '':
                setattr(model, model_attr, None)
                continue

            try:
                if field_type == bool:
                    value = True
                elif field_type == datetime.date:
                     value = datetime.strptime(value_str, '%Y-%m-%d').date() if value_str else None
                elif inspect.isclass(field_type) and issubclass(field_type, enum.Enum):
                    value = next((member for member in field_type if member.name == value_str or member.value == value_str), None)
                elif callable(field_type):
                    value = field_type(value_str)
                else:
                    value = field_type(value_str)

                setattr(model, model_attr, value)

            except (ValueError, TypeError, KeyError, StopIteration):
                pass
        
        elif field_type == bool:
            setattr(model, model_attr, False)