"""add user flow events and last screen fields

Revision ID: f9c8b7a6d5e4
Revises: c7d8e9f0a1b2
Create Date: 2026-03-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f9c8b7a6d5e4"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_screen_key", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("last_screen_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_users_last_screen_key"), "users", ["last_screen_key"], unique=False)

    op.create_table(
        "user_flow_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("screen_key", sa.String(length=64), nullable=True),
        sa.Column("action_key", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_flow_events_user_id"), "user_flow_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_flow_events_event_type"), "user_flow_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_user_flow_events_screen_key"), "user_flow_events", ["screen_key"], unique=False)
    op.create_index(op.f("ix_user_flow_events_action_key"), "user_flow_events", ["action_key"], unique=False)
    op.create_index(op.f("ix_user_flow_events_source"), "user_flow_events", ["source"], unique=False)
    op.create_index(op.f("ix_user_flow_events_created_at"), "user_flow_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_flow_events_created_at"), table_name="user_flow_events")
    op.drop_index(op.f("ix_user_flow_events_source"), table_name="user_flow_events")
    op.drop_index(op.f("ix_user_flow_events_action_key"), table_name="user_flow_events")
    op.drop_index(op.f("ix_user_flow_events_screen_key"), table_name="user_flow_events")
    op.drop_index(op.f("ix_user_flow_events_event_type"), table_name="user_flow_events")
    op.drop_index(op.f("ix_user_flow_events_user_id"), table_name="user_flow_events")
    op.drop_table("user_flow_events")

    op.drop_index(op.f("ix_users_last_screen_key"), table_name="users")
    op.drop_column("users", "last_screen_at")
    op.drop_column("users", "last_screen_key")
