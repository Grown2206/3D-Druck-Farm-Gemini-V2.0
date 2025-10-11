# migration_add_estimated_duration.py
"""Add estimated_print_duration_s to Job model

PROBLEM: Jobs können nicht korrekt geplant werden ohne Schätzung der Druckzeit!

Revision ID: add_estimated_duration
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    """Füge estimated_print_duration_s zum Job-Model hinzu."""
    
    with op.batch_alter_table('job', schema=None) as batch_op:
        # Kritisches Feld für Scheduler-Planung
        batch_op.add_column(sa.Column('estimated_print_duration_s', sa.Integer(), nullable=True))
        
        # Optional: Weitere sinnvolle Planungsfelder
        batch_op.add_column(sa.Column('estimated_material_g', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('complexity_score', sa.Integer(), nullable=True))

def downgrade():
    """Entferne die hinzugefügten Felder."""
    
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('complexity_score')
        batch_op.drop_column('estimated_material_g') 
        batch_op.drop_column('estimated_print_duration_s')
