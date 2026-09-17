"""Drop legacy subscription tables and payment.subscription_plan_id.

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-02-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for column in inspector.get_columns(table_name):
        if str(column.get("name")) == column_name:
            return True
    return False


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in set(inspector.get_table_names())


def upgrade() -> None:
    if _table_exists("payments") and _column_exists("payments", "subscription_plan_id"):
        with op.batch_alter_table("payments") as batch:
            batch.drop_column("subscription_plan_id")

    if _table_exists("user_subscriptions"):
        op.drop_table("user_subscriptions")
    if _table_exists("subscriptions"):
        op.drop_table("subscriptions")
    if _table_exists("subscription_plans"):
        op.drop_table("subscription_plans")


def downgrade() -> None:
    if not _table_exists("subscription_plans"):
        op.create_table(
            "subscription_plans",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
            sa.Column("request_amount", sa.Integer(), nullable=True),
            sa.Column("subscription_time_hours", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if not _table_exists("subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=True),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("quota_total", sa.Integer(), nullable=True),
            sa.Column("quota_used", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    if not _table_exists("user_subscriptions"):
        op.create_table(
            "user_subscriptions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("subscription_plan_id", sa.UUID(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("request_left", sa.Integer(), nullable=True),
            sa.Column("start_dt", sa.DateTime(), nullable=True),
            sa.Column("end_dt", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["subscription_plan_id"], ["subscription_plans.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
        op.create_index(
            "ix_user_subscriptions_subscription_plan_id",
            "user_subscriptions",
            ["subscription_plan_id"],
        )

    if _table_exists("payments") and not _column_exists("payments", "subscription_plan_id"):
        with op.batch_alter_table("payments") as batch:
            batch.add_column(
                sa.Column("subscription_plan_id", sa.UUID(), nullable=True)
            )
