"""Add new users only flag to promocodes.

Revision ID: c7d8e9f0a1b2
Revises: f2a1b3c4d5e6
Create Date: 2026-03-07 19:35:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = "f2a1b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("promocodes") as batch:
        batch.add_column(
            sa.Column("is_new_users_only", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.execute("UPDATE promocodes SET is_new_users_only = false WHERE is_new_users_only IS NULL")

    with op.batch_alter_table("promocodes") as batch:
        batch.alter_column("is_new_users_only", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("promocodes") as batch:
        batch.drop_column("is_new_users_only")
