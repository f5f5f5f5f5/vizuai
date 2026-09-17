"""add api idempotency keys table

Revision ID: e4f5a6b7c8d9
Revises: d9e8f7a6b5c4
Create Date: 2026-03-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4f5a6b7c8d9"
down_revision = "d9e8f7a6b5c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_idempotency_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "scope",
            "idempotency_key",
            name="uq_api_idempotency_keys_scope",
        ),
    )
    op.create_index(
        op.f("ix_api_idempotency_keys_account_id"),
        "api_idempotency_keys",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_idempotency_keys_scope"),
        "api_idempotency_keys",
        ["scope"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_idempotency_keys_status"),
        "api_idempotency_keys",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_idempotency_keys_created_at"),
        "api_idempotency_keys",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_api_idempotency_keys_created_at"), table_name="api_idempotency_keys")
    op.drop_index(op.f("ix_api_idempotency_keys_status"), table_name="api_idempotency_keys")
    op.drop_index(op.f("ix_api_idempotency_keys_scope"), table_name="api_idempotency_keys")
    op.drop_index(op.f("ix_api_idempotency_keys_account_id"), table_name="api_idempotency_keys")
    op.drop_table("api_idempotency_keys")
