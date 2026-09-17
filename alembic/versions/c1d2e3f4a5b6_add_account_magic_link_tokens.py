"""Add account magic link tokens table.

Revision ID: c1d2e3f4a5b6
Revises: a9b8c7d6e5f4
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_magic_link_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("redirect_path", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_account_magic_link_tokens_account_id"),
        "account_magic_link_tokens",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_magic_link_tokens_email"),
        "account_magic_link_tokens",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_magic_link_tokens_token_hash"),
        "account_magic_link_tokens",
        ["token_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_magic_link_tokens_status"),
        "account_magic_link_tokens",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_account_magic_link_tokens_status"),
        table_name="account_magic_link_tokens",
    )
    op.drop_index(
        op.f("ix_account_magic_link_tokens_token_hash"),
        table_name="account_magic_link_tokens",
    )
    op.drop_index(
        op.f("ix_account_magic_link_tokens_email"),
        table_name="account_magic_link_tokens",
    )
    op.drop_index(
        op.f("ix_account_magic_link_tokens_account_id"),
        table_name="account_magic_link_tokens",
    )
    op.drop_table("account_magic_link_tokens")
