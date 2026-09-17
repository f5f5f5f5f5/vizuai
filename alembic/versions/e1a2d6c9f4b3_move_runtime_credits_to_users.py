"""Move runtime credit balance fields from subscriptions to users.

Revision ID: e1a2d6c9f4b3
Revises: c4b7a9f2d1e3
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1a2d6c9f4b3"
down_revision: Union[str, Sequence[str], None] = "c4b7a9f2d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "credits_status",
                sa.String(length=32),
                nullable=False,
                server_default="no_credits",
            )
        )
        batch.add_column(
            sa.Column(
                "usage_left",
                sa.Integer(),
                nullable=True,
                server_default="0",
            )
        )

    op.execute(
        """
        WITH ranked AS (
          SELECT
            s.user_id,
            s.status,
            s.quota_total,
            s.quota_used,
            ROW_NUMBER() OVER (
              PARTITION BY s.user_id
              ORDER BY
                CASE WHEN s.status = 'active' THEN 0 ELSE 1 END,
                s.updated_at DESC NULLS LAST,
                s.created_at DESC NULLS LAST
            ) AS rn
          FROM subscriptions s
        )
        UPDATE users u
        SET
          usage_left = CASE
            WHEN r.status = 'active' AND r.quota_total IS NULL THEN NULL
            WHEN r.status = 'active' THEN GREATEST(COALESCE(r.quota_total, 0) - COALESCE(r.quota_used, 0), 0)
            ELSE 0
          END,
          credits_status = CASE
            WHEN r.status = 'active'
              AND (r.quota_total IS NULL OR GREATEST(COALESCE(r.quota_total, 0) - COALESCE(r.quota_used, 0), 0) > 0)
              THEN 'active'
            WHEN r.status = 'active' THEN 'exhausted'
            ELSE 'no_credits'
          END
        FROM ranked r
        WHERE r.rn = 1
          AND r.user_id = u.user_id
        """
    )

    with op.batch_alter_table("users") as batch:
        batch.alter_column("credits_status", server_default=None)
        batch.alter_column("usage_left", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("usage_left")
        batch.drop_column("credits_status")
