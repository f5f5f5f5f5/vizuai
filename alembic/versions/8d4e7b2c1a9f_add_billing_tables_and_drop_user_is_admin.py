"""Add billing tables and drop users.is_admin.

Revision ID: 8d4e7b2c1a9f
Revises: 6c3a8f1a2b7c
Create Date: 2026-02-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d4e7b2c1a9f"
down_revision: Union[str, Sequence[str], None] = "6c3a8f1a2b7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_admin")

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("request_amount", sa.Integer(), nullable=True),
        sa.Column("subscription_time_hours", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "promocodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code_string", sa.String(length=64), nullable=False),
        sa.Column("discount_type", sa.String(length=16), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("code_amount", sa.Integer(), nullable=True),
        sa.Column("code_left", sa.Integer(), nullable=True),
        sa.Column("max_uses_per_user", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_string"),
    )

    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_plan_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("request_left", sa.Integer(), nullable=True),
        sa.Column("start_dt", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.Column("end_dt", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["subscription_plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_subscriptions_user_id"), "user_subscriptions", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_user_subscriptions_subscription_plan_id"),
        "user_subscriptions",
        ["subscription_plan_id"],
        unique=False,
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subscription_plan_id", sa.UUID(), nullable=True),
        sa.Column("promocode_id", sa.UUID(), nullable=True),
        sa.Column("price_original", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0"),
        sa.Column("price_final", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["promocode_id"], ["promocodes.id"]),
        sa.ForeignKeyConstraint(["subscription_plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_payments_subscription_plan_id"),
        "payments",
        ["subscription_plan_id"],
        unique=False,
    )
    op.create_index(op.f("ix_payments_promocode_id"), "payments", ["promocode_id"], unique=False)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)
    op.create_index(
        op.f("ix_payments_provider_payment_id"),
        "payments",
        ["provider_payment_id"],
        unique=False,
    )

    op.create_table(
        "promocode_usages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["code_id"], ["promocodes.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promocode_usages_code_id"), "promocode_usages", ["code_id"], unique=False)
    op.create_index(op.f("ix_promocode_usages_user_id"), "promocode_usages", ["user_id"], unique=False)
    op.create_index(op.f("ix_promocode_usages_payment_id"), "promocode_usages", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promocode_usages_payment_id"), table_name="promocode_usages")
    op.drop_index(op.f("ix_promocode_usages_user_id"), table_name="promocode_usages")
    op.drop_index(op.f("ix_promocode_usages_code_id"), table_name="promocode_usages")
    op.drop_table("promocode_usages")

    op.drop_index(op.f("ix_payments_provider_payment_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_promocode_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_subscription_plan_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_user_id"), table_name="payments")
    op.drop_table("payments")

    op.drop_index(op.f("ix_user_subscriptions_subscription_plan_id"), table_name="user_subscriptions")
    op.drop_index(op.f("ix_user_subscriptions_user_id"), table_name="user_subscriptions")
    op.drop_table("user_subscriptions")

    op.drop_table("promocodes")
    op.drop_table("subscription_plans")

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("is_admin", sa.Boolean(), nullable=True))
