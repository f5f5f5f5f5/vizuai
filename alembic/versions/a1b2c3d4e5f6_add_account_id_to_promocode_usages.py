"""Add account ownership to promocode usages for web billing.

Revision ID: a1b2c3d4e5f6
Revises: f1e2d3c4b5a6
Create Date: 2026-03-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f1e2d3c4b5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("promocode_usages") as batch:
        batch.add_column(sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.create_index(op.f("ix_promocode_usages_account_id"), ["account_id"], unique=False)
        batch.create_foreign_key(
            "fk_promocode_usages_account_id_accounts",
            "accounts",
            ["account_id"],
            ["id"],
        )
        batch.alter_column("user_id", existing_type=sa.BigInteger(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("promocode_usages") as batch:
        batch.alter_column("user_id", existing_type=sa.BigInteger(), nullable=False)
        batch.drop_constraint("fk_promocode_usages_account_id_accounts", type_="foreignkey")
        batch.drop_index(op.f("ix_promocode_usages_account_id"))
        batch.drop_column("account_id")
