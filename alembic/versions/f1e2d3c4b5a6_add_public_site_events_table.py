"""add public site events table

Revision ID: f1e2d3c4b5a6
Revises: e4f5a6b7c8d9
Create Date: 2026-03-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1e2d3c4b5a6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_site_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("anon_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("screen_key", sa.String(length=64), nullable=True),
        sa.Column("action_key", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("referrer", sa.String(length=255), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_public_site_events_anon_id"), "public_site_events", ["anon_id"], unique=False)
    op.create_index(op.f("ix_public_site_events_event_type"), "public_site_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_public_site_events_screen_key"), "public_site_events", ["screen_key"], unique=False)
    op.create_index(op.f("ix_public_site_events_action_key"), "public_site_events", ["action_key"], unique=False)
    op.create_index(op.f("ix_public_site_events_source"), "public_site_events", ["source"], unique=False)
    op.create_index(op.f("ix_public_site_events_path"), "public_site_events", ["path"], unique=False)
    op.create_index(op.f("ix_public_site_events_created_at"), "public_site_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_public_site_events_created_at"), table_name="public_site_events")
    op.drop_index(op.f("ix_public_site_events_path"), table_name="public_site_events")
    op.drop_index(op.f("ix_public_site_events_source"), table_name="public_site_events")
    op.drop_index(op.f("ix_public_site_events_action_key"), table_name="public_site_events")
    op.drop_index(op.f("ix_public_site_events_screen_key"), table_name="public_site_events")
    op.drop_index(op.f("ix_public_site_events_event_type"), table_name="public_site_events")
    op.drop_index(op.f("ix_public_site_events_anon_id"), table_name="public_site_events")
    op.drop_table("public_site_events")
