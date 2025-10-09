"""Extended filament management

Revision ID: extended_filament_mgmt
Revises: 78a7ae2d500f
Create Date: 2025-01-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'extended_filament_mgmt'
down_revision = '78a7ae2d500f'
branch_labels = None
depends_on = None

def upgrade():
    # Erweitere FilamentType
    with op.batch_alter_table('filament_type', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avg_consumption_g_per_hour', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('shelf_life_months', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('storage_temperature_min', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('storage_temperature_max', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('storage_humidity_max', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('drying_temperature', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('drying_duration_hours', sa.Integer(), nullable=True))

    # Erweitere FilamentSpool
    with op.batch_alter_table('filament_spool', schema=None) as batch_op:
        batch_op.add_column(sa.Column('storage_location', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('batch_number', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('manufacturing_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('expiry_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('drying_end_time', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('drying_cycles_count', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('last_used_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('qr_code', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('weight_measurements', sqlite.JSON(), nullable=True))
        batch_op.add_column(sa.Column('usage_history', sqlite.JSON(), nullable=True))

    # Neue Tabelle: FilamentUsageLog
    op.create_table('filament_usage_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spool_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('weight_before_g', sa.Float(), nullable=False),
        sa.Column('weight_after_g', sa.Float(), nullable=False),
        sa.Column('usage_g', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['job.id'], ),
        sa.ForeignKeyConstraint(['spool_id'], ['filament_spool.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Neue Tabelle: StorageLocation
    op.create_table('storage_location',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_spools', sa.Integer(), nullable=True),
        sa.Column('temperature_controlled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('humidity_controlled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # Neue Tabelle: DryingSession
    op.create_table('drying_session',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spool_id', sa.Integer(), nullable=False),
        sa.Column('temperature', sa.Integer(), nullable=False),
        sa.Column('duration_hours', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('actual_end_time', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['spool_id'], ['filament_spool.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('drying_session')
    op.drop_table('storage_location')
    op.drop_table('filament_usage_log')
    
    with op.batch_alter_table('filament_spool', schema=None) as batch_op:
        batch_op.drop_column('usage_history')
        batch_op.drop_column('weight_measurements')
        batch_op.drop_column('qr_code')
        batch_op.drop_column('last_used_date')
        batch_op.drop_column('drying_cycles_count')
        batch_op.drop_column('drying_end_time')
        batch_op.drop_column('expiry_date')
        batch_op.drop_column('manufacturing_date')
        batch_op.drop_column('batch_number')
        batch_op.drop_column('storage_location')
    
    with op.batch_alter_table('filament_type', schema=None) as batch_op:
        batch_op.drop_column('drying_duration_hours')
        batch_op.drop_column('drying_temperature')
        batch_op.drop_column('storage_humidity_max')
        batch_op.drop_column('storage_temperature_max')
        batch_op.drop_column('storage_temperature_min')
        batch_op.drop_column('shelf_life_months')
        batch_op.drop_column('avg_consumption_g_per_hour')