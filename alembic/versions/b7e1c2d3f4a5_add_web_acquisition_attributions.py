"""Add durable web acquisition attribution table.

Revision ID: b7e1c2d3f4a5
Revises: a1b2c3d4e5f6
Create Date: 2026-03-30 23:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b7e1c2d3f4a5"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_acquisition_attributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anon_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_utm_source", sa.String(length=255), nullable=True),
        sa.Column("first_utm_medium", sa.String(length=255), nullable=True),
        sa.Column("first_utm_campaign", sa.String(length=255), nullable=True),
        sa.Column("first_utm_content", sa.String(length=255), nullable=True),
        sa.Column("first_utm_term", sa.String(length=255), nullable=True),
        sa.Column("first_landing_host", sa.String(length=255), nullable=True),
        sa.Column("first_landing_path", sa.String(length=255), nullable=True),
        sa.Column("first_referrer", sa.String(length=1024), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("linked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_web_acquisition_attributions_anon_id"), "web_acquisition_attributions", ["anon_id"], unique=True)
    op.create_index(op.f("ix_web_acquisition_attributions_account_id"), "web_acquisition_attributions", ["account_id"], unique=False)
    op.create_index(op.f("ix_web_acquisition_attributions_first_utm_source"), "web_acquisition_attributions", ["first_utm_source"], unique=False)
    op.create_index(op.f("ix_web_acquisition_attributions_first_utm_medium"), "web_acquisition_attributions", ["first_utm_medium"], unique=False)
    op.create_index(op.f("ix_web_acquisition_attributions_first_utm_campaign"), "web_acquisition_attributions", ["first_utm_campaign"], unique=False)
    op.create_index(op.f("ix_web_acquisition_attributions_first_seen_at"), "web_acquisition_attributions", ["first_seen_at"], unique=False)
    op.create_index(op.f("ix_web_acquisition_attributions_last_seen_at"), "web_acquisition_attributions", ["last_seen_at"], unique=False)
    op.create_index(op.f("ix_web_acquisition_attributions_linked_at"), "web_acquisition_attributions", ["linked_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_web_acquisition_attributions_linked_at"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_last_seen_at"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_first_seen_at"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_first_utm_campaign"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_first_utm_medium"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_first_utm_source"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_account_id"), table_name="web_acquisition_attributions")
    op.drop_index(op.f("ix_web_acquisition_attributions_anon_id"), table_name="web_acquisition_attributions")
    op.drop_table("web_acquisition_attributions")
