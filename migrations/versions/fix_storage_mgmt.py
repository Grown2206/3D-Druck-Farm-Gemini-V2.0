"""Fix storage management migration

Revision ID: fix_storage_mgmt
Revises: ed440967a2ab
Create Date: 2025-01-10

"""
from alembic import op
import sqlalchemy as sa
import datetime

revision = 'fix_storage_mgmt'
down_revision = 'ed440967a2ab'
branch_labels = None
depends_on = None

def upgrade():
    # Lösche die problematische Tabelle falls sie existiert
    op.drop_table('predefined_storage_locations')
    
    # Erstelle sie erneut mit korrekten Daten
    storage_locations_table = op.create_table('predefined_storage_locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_spools', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    
    # Mit Python datetime statt sa.text()
    current_time = datetime.datetime.utcnow()
    
    op.bulk_insert(storage_locations_table, [
        {'code': 'A1', 'name': 'Regal A - Ebene 1', 'description': 'PLA und PETG Filamente', 'max_spools': 20, 'is_active': True, 'created_at': current_time},
        {'code': 'A2', 'name': 'Regal A - Ebene 2', 'description': 'ABS und Hochtemperatur-Filamente', 'max_spools': 20, 'is_active': True, 'created_at': current_time},
        {'code': 'B1', 'name': 'Regal B - Ebene 1', 'description': 'Flexible Filamente', 'max_spools': 15, 'is_active': True, 'created_at': current_time},
        {'code': 'B2', 'name': 'Regal B - Ebene 2', 'description': 'Spezial-Filamente', 'max_spools': 15, 'is_active': True, 'created_at': current_time},
        {'code': 'C1', 'name': 'Klimaschrank', 'description': 'Feuchtigkeitsempfindliche Materialien', 'max_spools': 10, 'is_active': True, 'created_at': current_time},
        {'code': 'QUARANTINE', 'name': 'Quarantäne', 'description': 'Neue oder problematische Spulen', 'max_spools': 5, 'is_active': True, 'created_at': current_time},
    ])

def downgrade():
    op.drop_table('predefined_storage_locations')