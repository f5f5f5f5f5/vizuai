"""Update design schema for simple pipeline

Revision ID: 5b1a1c9d3f2a
Revises: 04b65143d9fd
Create Date: 2026-02-06 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5b1a1c9d3f2a"
down_revision: Union[str, Sequence[str], None] = "04b65143d9fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("designs") as batch:
        batch.alter_column("design_image_url", new_column_name="final_image_url")
        batch.alter_column("completed_at", new_column_name="ended_at")
        batch.drop_column("generated_prompt")
        batch.add_column(sa.Column("prepared_image_url", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("render_image_url", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("fix_image_url", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("selected_image", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("score_render", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("score_fix", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("providers_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("debug_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("error_stage", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("pipeline_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("designs") as batch:
        batch.drop_column("pipeline_version")
        batch.drop_column("error_stage")
        batch.drop_column("debug_json")
        batch.drop_column("providers_json")
        batch.drop_column("score_fix")
        batch.drop_column("score_render")
        batch.drop_column("selected_image")
        batch.drop_column("fix_image_url")
        batch.drop_column("render_image_url")
        batch.drop_column("prepared_image_url")
        batch.add_column(sa.Column("generated_prompt", sa.Text(), nullable=True))
        batch.alter_column("final_image_url", new_column_name="design_image_url")
        batch.alter_column("ended_at", new_column_name="completed_at")
