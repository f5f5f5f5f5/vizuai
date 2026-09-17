"""Add billing webhook events table for idempotency/dead-letter flow.

Revision ID: a7b8c9d0e1f2
Revises: e1a2d6c9f4b3
Create Date: 2026-02-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "e1a2d6c9f4b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=191), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "idempotency_key", name="uq_billing_webhook_provider_idem"),
    )
    op.create_index("ix_billing_webhook_events_provider", "billing_webhook_events", ["provider"])
    op.create_index("ix_billing_webhook_events_event_type", "billing_webhook_events", ["event_type"])
    op.create_index(
        "ix_billing_webhook_events_idempotency_key",
        "billing_webhook_events",
        ["idempotency_key"],
    )
    op.create_index("ix_billing_webhook_events_status", "billing_webhook_events", ["status"])
    op.create_index("ix_billing_webhook_events_order_id", "billing_webhook_events", ["order_id"])
    op.create_index(
        "ix_billing_webhook_events_provider_payment_id",
        "billing_webhook_events",
        ["provider_payment_id"],
    )
    op.create_index(
        "ix_billing_webhook_events_last_seen_at",
        "billing_webhook_events",
        ["last_seen_at"],
    )
    op.create_index(
        "ix_billing_webhook_events_processed_at",
        "billing_webhook_events",
        ["processed_at"],
    )
    op.create_index(
        "ix_billing_webhook_events_created_at",
        "billing_webhook_events",
        ["created_at"],
    )
    op.create_index(
        "ix_billing_webhook_events_updated_at",
        "billing_webhook_events",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_billing_webhook_events_updated_at", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_created_at", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_processed_at", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_last_seen_at", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_provider_payment_id", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_order_id", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_status", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_idempotency_key", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_event_type", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_provider", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
