# Lösung 1: Migration zurücksetzen und neu erstellen

# Schritt 1: Migration zurücksetzen
# flask db downgrade

# Schritt 2: Die automatisch erstellte Migration in migrations/versions/ löschen
# (Die Datei die mit "extend_consumables..." beginnt)

# Schritt 3: Neue Migration mit Server-Defaults erstellen
# Erstelle eine neue Datei in migrations/versions/ oder bearbeite die bestehende:

"""Extend consumables model with advanced features

Revision ID: f953499bc20c
Revises: 9897bd9645b1
Create Date: 2025-01-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'f953499bc20c'
down_revision = '9897bd9645b1'
branch_labels = None
depends_on = None


def upgrade():
    # Erstelle die consumable_printers Association Table
    op.create_table('consumable_printers',
        sa.Column('consumable_id', sa.Integer(), nullable=False),
        sa.Column('printer_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['consumable_id'], ['consumable.id'], ),
        sa.ForeignKeyConstraint(['printer_id'], ['printer.id'], ),
        sa.PrimaryKeyConstraint('consumable_id', 'printer_id')
    )
    
    # Batch-Operationen für SQLite
    with op.batch_alter_table('consumable', schema=None) as batch_op:
        # Neue Spalten mit Server Defaults hinzufügen
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('usage_description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('min_stock', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_stock', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('storage_location', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('manufacturer', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('supplier', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('article_number', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('ean', sa.String(length=13), nullable=True))
        batch_op.add_column(sa.Column('unit_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('currency', sa.String(length=10), server_default='EUR', nullable=True))
        batch_op.add_column(sa.Column('last_ordered_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('last_order_quantity', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('has_expiry', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('expiry_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('image_filename', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('datasheet_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('hazard_symbols', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('safety_warnings', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('specifications', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('compatibility_tags', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('consumable', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('compatibility_tags')
        batch_op.drop_column('specifications')
        batch_op.drop_column('safety_warnings')
        batch_op.drop_column('hazard_symbols')
        batch_op.drop_column('datasheet_url')
        batch_op.drop_column('image_filename')
        batch_op.drop_column('expiry_date')
        batch_op.drop_column('has_expiry')
        batch_op.drop_column('last_order_quantity')
        batch_op.drop_column('last_ordered_date')
        batch_op.drop_column('currency')
        batch_op.drop_column('unit_price')
        batch_op.drop_column('ean')
        batch_op.drop_column('article_number')
        batch_op.drop_column('supplier')
        batch_op.drop_column('manufacturer')
        batch_op.drop_column('storage_location')
        batch_op.drop_column('max_stock')
        batch_op.drop_column('min_stock')
        batch_op.drop_column('usage_description')
        batch_op.drop_column('description')
    
    op.drop_table('consumable_printers')