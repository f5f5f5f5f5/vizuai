"""Normalize T-Bank billing event amounts from kopecks to RUB units.

Revision ID: d4e5f6a7b8c9
Revises: b3f4a7d9e1c2, b1c2d3e4f5a6
Create Date: 2026-02-27
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = ("b3f4a7d9e1c2", "b1c2d3e4f5a6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE billing_events be
        SET stars_amount = CAST(be.stars_amount / 100 AS INTEGER)
        FROM payments p
        WHERE be.payment_id = p.id
          AND be.provider = 'tbank_sbp'
          AND COALESCE(be.currency, '') = 'RUB'
          AND be.stars_amount IS NOT NULL
          AND be.stars_amount = CAST((p.price_final * 100) AS INTEGER)
        """
    )


def downgrade() -> None:
    # Irreversible data normalization migration.
    pass

