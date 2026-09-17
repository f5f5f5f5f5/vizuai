"""Add user acquisition source fields.

Revision ID: f2a1b3c4d5e6
Revises: e6f7a8b9c0d1
Create Date: 2026-03-07 19:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a1b3c4d5e6"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("acquisition_source", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("acquisition_recorded_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_users_acquisition_source", ["acquisition_source"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_acquisition_source")
        batch.drop_column("acquisition_recorded_at")
        batch.drop_column("acquisition_source")
