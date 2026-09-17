"""Add promocode reservation state fields.

Revision ID: b3f4a7d9e1c2
Revises: ab12cd34ef56
Create Date: 2026-02-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f4a7d9e1c2"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("promocode_usages") as batch:
        batch.add_column(
            sa.Column("status", sa.String(length=32), nullable=False, server_default="redeemed")
        )
        batch.add_column(sa.Column("reserved_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("released_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("redeemed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("release_reason", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("credits_amount", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("price_original", sa.Numeric(precision=10, scale=2), nullable=True))
        batch.add_column(sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=True))
        batch.add_column(sa.Column("price_final", sa.Numeric(precision=10, scale=2), nullable=True))
        batch.create_index("ix_promocode_usages_status", ["status"], unique=False)
        batch.create_index("ix_promocode_usages_expires_at", ["expires_at"], unique=False)

    op.execute("UPDATE promocode_usages SET status='redeemed' WHERE status IS NULL")
    op.execute("UPDATE promocode_usages SET redeemed_at=used_at WHERE redeemed_at IS NULL")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_promocode_usages_payment_id_not_null
        ON promocode_usages (payment_id)
        WHERE payment_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_promocode_usages_payment_id_not_null")
    with op.batch_alter_table("promocode_usages") as batch:
        batch.drop_index("ix_promocode_usages_expires_at")
        batch.drop_index("ix_promocode_usages_status")
        batch.drop_column("price_final")
        batch.drop_column("discount_amount")
        batch.drop_column("price_original")
        batch.drop_column("credits_amount")
        batch.drop_column("release_reason")
        batch.drop_column("redeemed_at")
        batch.drop_column("released_at")
        batch.drop_column("expires_at")
        batch.drop_column("reserved_at")
        batch.drop_column("status")
