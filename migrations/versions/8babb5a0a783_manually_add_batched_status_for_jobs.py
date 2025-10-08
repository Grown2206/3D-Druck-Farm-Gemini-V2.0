"""Manually add BATCHED status for jobs

Revision ID: 8babb5a0a783
Revises: 990b52749fee
Create Date: 2025-09-24 17:15:39.251445

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8babb5a0a783' # Hier die neue ID aus dem Dateinamen einfügen
down_revision = '990b52749fee'       # Die ID der vorherigen Migration
branch_labels = None
depends_on = None


def upgrade():
    # Da die zugrunde liegende Spalte VARCHAR ist, ist keine Schema-Änderung erforderlich.
    # Wir benötigen diesen Migrationsschritt nur, damit Alembic die Änderung in der Enum-Definition nachverfolgen kann.
    pass


def downgrade():
    # Ebenso ist hier keine Aktion für das Downgrade erforderlich.
    pass
