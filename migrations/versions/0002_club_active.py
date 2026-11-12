"""Add persistent club deactivation without deleting related records.

Revision ID: 0002_club_active
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_club_active"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # Existing clubs become active. No existing constraints or records are removed.
    op.add_column("clubs", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade():
    # Not executed: removing this column discards deactivation state.
    op.drop_column("clubs", "is_active")
