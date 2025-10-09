"""Add storage management support

Revision ID: ed440967a2ab
Revises: extended_filament_mgmt
Create Date: 2025-10-09 00:38:06.285287

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = 'ed440967a2ab'
down_revision = 'extended_filament_mgmt'
branch_labels = None
depends_on = None

def upgrade():
    # Überprüfe, ob storage_location bereits existiert, falls nicht hinzufügen
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Prüfe FilamentSpool Spalten
    filament_spool_columns = [col['name'] for col in inspector.get_columns('filament_spool')]
    
    # Erweitere FilamentSpool falls storage_location fehlt
    if 'storage_location' not in filament_spool_columns:
        with op.batch_alter_table('filament_spool', schema=None) as batch_op:
            batch_op.add_column(sa.Column('storage_location', sa.String(length=100), nullable=True))
    
    # Füge Standard-Lagerorte hinzu
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
    
    # Standard-Lagerorte einfügen mit Python datetime
    import datetime
    current_time = datetime.datetime.utcnow()
   
    op.bulk_insert(storage_locations_table, [
       {'code': 'A1', 'name': 'Regal A - Ebene 1', 'description': 'PLA und PETG Filamente', 'max_spools': 20, 'is_active': True, 'created_at': current_time},
       {'code': 'A2', 'name': 'Regal A - Ebene 2', 'description': 'ABS und Hochtemperatur-Filamente', 'max_spools': 20, 'is_active': True, 'created_at': current_time},
       {'code': 'B1', 'name': 'Regal B - Ebene 1', 'description': 'Flexible Filamente', 'max_spools': 15, 'is_active': True, 'created_at': current_time},
       {'code': 'B2', 'name': 'Regal B - Ebene 2', 'description': 'Spezial-Filamente', 'max_spools': 15, 'is_active': True, 'created_at': current_time},
       {'code': 'C1', 'name': 'Klimaschrank', 'description': 'Feuchtigkeitsempfindliche Materialien', 'max_spools': 10, 'is_active': True, 'created_at': current_time},
       {'code': 'QUARANTINE', 'name': 'Quarantäne', 'description': 'Neue oder problematische Spulen', 'max_spools': 5, 'is_active': True, 'created_at': current_time},
    ])
    
    # Spulen-Bewegungslog für Tracking
    op.create_table('spool_movement_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spool_id', sa.Integer(), nullable=False),
        sa.Column('from_location', sa.String(length=100), nullable=True),
        sa.Column('to_location', sa.String(length=100), nullable=True),
        sa.Column('moved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['spool_id'], ['filament_spool.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['moved_by_user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Index für bessere Performance
    op.create_index('idx_spool_movement_spool', 'spool_movement_log', ['spool_id'])
    op.create_index('idx_spool_movement_timestamp', 'spool_movement_log', ['timestamp'])
    
    # Index für storage_location in filament_spool
    op.create_index('idx_filament_spool_storage', 'filament_spool', ['storage_location'])

def downgrade():
    op.drop_index('idx_filament_spool_storage', table_name='filament_spool')
    op.drop_index('idx_spool_movement_timestamp', table_name='spool_movement_log')
    op.drop_index('idx_spool_movement_spool', table_name='spool_movement_log')
    op.drop_table('spool_movement_log')
    op.drop_table('predefined_storage_locations')
    
    # storage_location in filament_spool belassen, da es eventuell von vorheriger Migration stammt