"""Add Telegram Stars refund fields to payments.

Revision ID: f7c9b8a1d2e4
Revises: e1a2d6c9f4b3
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7c9b8a1d2e4"
down_revision: Union[str, Sequence[str], None] = "e1a2d6c9f4b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("telegram_payment_charge_id", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column(
                "credits_amount",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("refund_reason", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("refunded_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_payments_telegram_payment_charge_id", ["telegram_payment_charge_id"], unique=False)
        batch.alter_column("credits_amount", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch:
        batch.drop_index("ix_payments_telegram_payment_charge_id")
        batch.drop_column("refunded_at")
        batch.drop_column("refund_reason")
        batch.drop_column("credits_amount")
        batch.drop_column("telegram_payment_charge_id")
