"""Add new maintenance system

Revision ID: 78a7ae2d500f
Revises: e0f98318ecdb
Create Date: 2025-01-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '78a7ae2d500f'
down_revision = 'e0f98318ecdb'
branch_labels = None
depends_on = None

# Temporäre Enum-Definition für die Migration
def upgrade():
    # MaintenanceTaskNew
    op.create_table('maintenance_task_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.VARCHAR(length=50), nullable=False),  # Statt models.RobustEnum()
        sa.Column('interval_type', sa.VARCHAR(length=50), nullable=True),
        sa.Column('interval_value', sa.Integer(), nullable=True),
        sa.Column('priority', sa.VARCHAR(length=50), nullable=True),
        sa.Column('estimated_duration_min', sa.Integer(), nullable=True),
        sa.Column('checklist_items', sqlite.JSON(), nullable=True),
        sa.Column('instruction_url', sa.String(length=255), nullable=True),
        sa.Column('instruction_pdf', sa.String(length=255), nullable=True),
        sa.Column('video_tutorial_url', sa.String(length=255), nullable=True),
        sa.Column('safety_warnings', sqlite.JSON(), nullable=True),
        sa.Column('applicable_to_all', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('title')
    )

    # TaskConsumableNew
    op.create_table('task_consumable_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('consumable_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['consumable_id'], ['consumable.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['maintenance_task_new.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # MaintenanceScheduleNew
    op.create_table('maintenance_schedule_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=False),
        sa.Column('scheduled_date', sa.DateTime(), nullable=False),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('status', sa.VARCHAR(length=50), nullable=True),
        sa.Column('priority', sa.VARCHAR(length=50), nullable=True),
        sa.Column('triggered_by', sa.String(length=50), nullable=True),
        sa.Column('trigger_value', sa.Float(), nullable=True),
        sa.Column('assigned_to_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to_user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['printer_id'], ['printer.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['maintenance_task_new.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # MaintenanceExecutionNew
    op.create_table('maintenance_execution_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=False),
        sa.Column('performed_by_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('actual_duration_min', sa.Integer(), nullable=True),
        sa.Column('checklist_results', sqlite.JSON(), nullable=True),
        sa.Column('issues_found', sa.Text(), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('next_maintenance_recommended', sa.Date(), nullable=True),
        sa.Column('labor_cost', sa.Float(), nullable=True),
        sa.Column('parts_cost', sa.Float(), nullable=True),
        sa.Column('total_cost', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('parts_ordered', sqlite.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['performed_by_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['printer_id'], ['printer.id'], ),
        sa.ForeignKeyConstraint(['schedule_id'], ['maintenance_schedule_new.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['maintenance_task_new.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ExecutionConsumableNew
    op.create_table('execution_consumable_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.Integer(), nullable=False),
        sa.Column('consumable_id', sa.Integer(), nullable=False),
        sa.Column('quantity_used', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['consumable_id'], ['consumable.id'], ),
        sa.ForeignKeyConstraint(['execution_id'], ['maintenance_execution_new.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # MaintenancePhotoNew
    op.create_table('maintenance_photo_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('execution_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('caption', sa.String(length=255), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['maintenance_execution_new.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Association Table
    op.create_table('task_printer_assignment',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['printer_id'], ['printer.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['maintenance_task_new.id'], ),
        sa.PrimaryKeyConstraint('task_id', 'printer_id')
    )


def downgrade():
    # Tabellen in umgekehrter Reihenfolge löschen
    op.drop_table('task_printer_assignment')
    op.drop_table('maintenance_photo_new')
    op.drop_table('execution_consumable_new')
    op.drop_table('maintenance_execution_new')
    op.drop_table('maintenance_schedule_new')
    op.drop_table('task_consumable_new')
    op.drop_table('maintenance_task_new')