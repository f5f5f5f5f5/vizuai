"""Add provider_amount to billing_events and backfill values.

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-02-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billing_events",
        sa.Column("provider_amount", sa.Numeric(10, 2), nullable=True),
    )

    # Backfill from legacy integer amount field.
    # XTR: integer units are already correct.
    op.execute(
        """
        UPDATE billing_events
        SET provider_amount = CAST(stars_amount AS NUMERIC(10,2))
        WHERE stars_amount IS NOT NULL
          AND COALESCE(currency, '') = 'XTR'
          AND provider_amount IS NULL
        """
    )

    # RUB: infer whether legacy value was rubles or kopecks using related payment amount.
    op.execute(
        """
        UPDATE billing_events be
        SET provider_amount = (
          CASE
            WHEN be.stars_amount IS NULL THEN NULL
            WHEN p.id IS NULL THEN ROUND((be.stars_amount::numeric / 100.0), 2)
            WHEN be.stars_amount = CAST(ROUND(p.price_final * 100.0, 0) AS INTEGER) THEN CAST(p.price_final AS NUMERIC(10,2))
            WHEN be.stars_amount = CAST(ROUND(p.price_final, 0) AS INTEGER)
                 AND p.price_final = TRUNC(p.price_final) THEN CAST(p.price_final AS NUMERIC(10,2))
            ELSE ROUND((be.stars_amount::numeric / 100.0), 2)
          END
        )
        FROM payments p
        WHERE be.payment_id = p.id
          AND be.provider_amount IS NULL
          AND COALESCE(be.currency, '') = 'RUB'
        """
    )

    # For RUB events without linked payment, assume legacy value is in kopecks.
    op.execute(
        """
        UPDATE billing_events be
        SET provider_amount = ROUND((be.stars_amount::numeric / 100.0), 2)
        WHERE be.payment_id IS NULL
          AND be.provider_amount IS NULL
          AND be.stars_amount IS NOT NULL
          AND COALESCE(be.currency, '') = 'RUB'
        """
    )


def downgrade() -> None:
    op.drop_column("billing_events", "provider_amount")

