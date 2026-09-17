"""Expand design URL columns to TEXT.

Revision ID: 6c3a8f1a2b7c
Revises: 5b1a1c9d3f2a
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6c3a8f1a2b7c"
down_revision = "5b1a1c9d3f2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("designs", "original_image_url", type_=sa.Text(), existing_type=sa.String(length=512))
    op.alter_column("designs", "prepared_image_url", type_=sa.Text(), existing_type=sa.String(length=512))
    op.alter_column("designs", "render_image_url", type_=sa.Text(), existing_type=sa.String(length=512))
    op.alter_column("designs", "fix_image_url", type_=sa.Text(), existing_type=sa.String(length=512))
    op.alter_column("designs", "final_image_url", type_=sa.Text(), existing_type=sa.String(length=512))


def downgrade() -> None:
    op.alter_column("designs", "final_image_url", type_=sa.String(length=512), existing_type=sa.Text())
    op.alter_column("designs", "fix_image_url", type_=sa.String(length=512), existing_type=sa.Text())
    op.alter_column("designs", "render_image_url", type_=sa.String(length=512), existing_type=sa.Text())
    op.alter_column("designs", "prepared_image_url", type_=sa.String(length=512), existing_type=sa.Text())
    op.alter_column("designs", "original_image_url", type_=sa.String(length=512), existing_type=sa.Text())
