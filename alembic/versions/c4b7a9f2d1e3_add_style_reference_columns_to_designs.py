"""Add style reference columns to designs.

Revision ID: c4b7a9f2d1e3
Revises: 9f2c7b8a1d4e
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4b7a9f2d1e3"
down_revision: Union[str, Sequence[str], None] = "9f2c7b8a1d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("designs") as batch:
        batch.add_column(sa.Column("style_reference_image_url", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "style_reference_used",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch.add_column(sa.Column("style_reference_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("designs") as batch:
        batch.drop_column("style_reference_status")
        batch.drop_column("style_reference_used")
        batch.drop_column("style_reference_image_url")
