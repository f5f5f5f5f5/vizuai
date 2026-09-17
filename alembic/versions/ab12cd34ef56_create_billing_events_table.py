"""Create billing_events table for billing reconciliation reports.

Revision ID: ab12cd34ef56
Revises: f7c9b8a1d2e4
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "f7c9b8a1d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("telegram_payment_charge_id", sa.String(length=128), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("stars_amount", sa.Integer(), nullable=True),
        sa.Column("credits_amount", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=128), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_billing_events_created_at"), "billing_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_billing_events_event_type"), "billing_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_billing_events_payment_id"), "billing_events", ["payment_id"], unique=False)
    op.create_index(
        op.f("ix_billing_events_provider_payment_id"),
        "billing_events",
        ["provider_payment_id"],
        unique=False,
    )
    op.create_index(op.f("ix_billing_events_provider"), "billing_events", ["provider"], unique=False)
    op.create_index(
        op.f("ix_billing_events_reason"),
        "billing_events",
        ["reason"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_events_telegram_payment_charge_id"),
        "billing_events",
        ["telegram_payment_charge_id"],
        unique=False,
    )
    op.create_index(op.f("ix_billing_events_user_id"), "billing_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_billing_events_user_id"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_telegram_payment_charge_id"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_reason"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_provider"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_provider_payment_id"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_payment_id"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_event_type"), table_name="billing_events")
    op.drop_index(op.f("ix_billing_events_created_at"), table_name="billing_events")
    op.drop_table("billing_events")
