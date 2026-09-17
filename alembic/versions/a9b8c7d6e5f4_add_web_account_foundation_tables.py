"""Add web account foundation tables and ownership columns.

Revision ID: a9b8c7d6e5f4
Revises: f9c8b7a6d5e4
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f9c8b7a6d5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("primary_email", sa.String(length=320), nullable=True),
        sa.Column("primary_phone", sa.String(length=32), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locale", sa.String(length=16), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_accounts_status"), "accounts", ["status"], unique=False)
    op.create_index(op.f("ix_accounts_primary_email"), "accounts", ["primary_email"], unique=False)

    op.create_table(
        "account_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=320), nullable=True),
        sa.Column("provider_phone", sa.String(length=32), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_account_identities_provider_user"
        ),
    )
    op.create_index(
        op.f("ix_account_identities_account_id"), "account_identities", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_account_identities_provider"), "account_identities", ["provider"], unique=False
    )
    op.create_index(
        op.f("ix_account_identities_provider_email"),
        "account_identities",
        ["provider_email"],
        unique=False,
    )

    op.create_table(
        "account_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=255), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("device_meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token_hash"),
    )
    op.create_index(
        op.f("ix_account_sessions_account_id"), "account_sessions", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_account_sessions_session_token_hash"),
        "account_sessions",
        ["session_token_hash"],
        unique=False,
    )
    op.create_index(op.f("ix_account_sessions_status"), "account_sessions", ["status"], unique=False)

    op.create_table(
        "design_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("source_image_url", sa.Text(), nullable=False),
        sa.Column("prepared_image_url", sa.Text(), nullable=True),
        sa.Column("style_reference_image_url", sa.Text(), nullable=True),
        sa.Column("style_reference_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column("estimated_units", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_design_drafts_account_id"), "design_drafts", ["account_id"], unique=False)
    op.create_index(op.f("ix_design_drafts_status"), "design_drafts", ["status"], unique=False)

    op.create_table(
        "furniture_search_drafts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("source_image_url", sa.Text(), nullable=False),
        sa.Column("prepared_image_url", sa.Text(), nullable=True),
        sa.Column("user_request", sa.Text(), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column("estimated_units", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_furniture_search_drafts_account_id"),
        "furniture_search_drafts",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_furniture_search_drafts_status"),
        "furniture_search_drafts",
        ["status"],
        unique=False,
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("draft_id", sa.UUID(), nullable=True),
        sa.Column("draft_type", sa.String(length=32), nullable=True),
        sa.Column("result_ref_type", sa.String(length=32), nullable=True),
        sa.Column("result_ref_id", sa.UUID(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_stage", sa.String(length=64), nullable=True),
        sa.Column("units_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("units_final", sa.Integer(), nullable=True),
        sa.Column("provider_meta_json", sa.JSON(), nullable=True),
        sa.Column("progress_meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_account_id"), "jobs", ["account_id"], unique=False)
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_draft_id"), "jobs", ["draft_id"], unique=False)
    op.create_index(op.f("ix_jobs_result_ref_id"), "jobs", ["result_ref_id"], unique=False)
    op.create_index(op.f("ix_jobs_error_code"), "jobs", ["error_code"], unique=False)

    op.create_table(
        "checkout_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("credits_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("amount_original", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("amount_final", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("provider_checkout_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_checkout_sessions_account_id"), "checkout_sessions", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_checkout_sessions_provider"), "checkout_sessions", ["provider"], unique=False
    )
    op.create_index(
        op.f("ix_checkout_sessions_status"), "checkout_sessions", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_checkout_sessions_provider_checkout_id"),
        "checkout_sessions",
        ["provider_checkout_id"],
        unique=False,
    )

    op.create_table(
        "account_flow_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("screen_key", sa.String(length=64), nullable=True),
        sa.Column("action_key", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_flow_events_account_id"),
        "account_flow_events",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_flow_events_event_type"),
        "account_flow_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_flow_events_screen_key"),
        "account_flow_events",
        ["screen_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_flow_events_action_key"),
        "account_flow_events",
        ["action_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_flow_events_source"), "account_flow_events", ["source"], unique=False
    )
    op.create_index(
        op.f("ix_account_flow_events_created_at"),
        "account_flow_events",
        ["created_at"],
        unique=False,
    )

    with op.batch_alter_table("designs") as batch:
        batch.add_column(sa.Column("account_id", sa.UUID(), nullable=True))
        batch.add_column(sa.Column("job_id", sa.UUID(), nullable=True))
        batch.add_column(sa.Column("draft_id", sa.UUID(), nullable=True))
        batch.create_index("ix_designs_account_id", ["account_id"], unique=False)
        batch.create_index("ix_designs_job_id", ["job_id"], unique=False)
        batch.create_index("ix_designs_draft_id", ["draft_id"], unique=False)
        batch.create_foreign_key("fk_designs_account_id_accounts", "accounts", ["account_id"], ["id"])
        batch.create_foreign_key("fk_designs_job_id_jobs", "jobs", ["job_id"], ["id"])
        batch.create_foreign_key(
            "fk_designs_draft_id_design_drafts", "design_drafts", ["draft_id"], ["id"]
        )

    with op.batch_alter_table("payments") as batch:
        batch.alter_column("user_id", existing_type=sa.BigInteger(), nullable=True)
        batch.add_column(sa.Column("account_id", sa.UUID(), nullable=True))
        batch.add_column(sa.Column("checkout_session_id", sa.UUID(), nullable=True))
        batch.create_index("ix_payments_account_id", ["account_id"], unique=False)
        batch.create_index("ix_payments_checkout_session_id", ["checkout_session_id"], unique=False)
        batch.create_foreign_key("fk_payments_account_id_accounts", "accounts", ["account_id"], ["id"])
        batch.create_foreign_key(
            "fk_payments_checkout_session_id_checkout_sessions",
            "checkout_sessions",
            ["checkout_session_id"],
            ["id"],
        )

    with op.batch_alter_table("billing_events") as batch:
        batch.add_column(sa.Column("account_id", sa.UUID(), nullable=True))
        batch.create_index("ix_billing_events_account_id", ["account_id"], unique=False)
        batch.create_foreign_key(
            "fk_billing_events_account_id_accounts", "accounts", ["account_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("billing_events") as batch:
        batch.drop_constraint("fk_billing_events_account_id_accounts", type_="foreignkey")
        batch.drop_index("ix_billing_events_account_id")
        batch.drop_column("account_id")

    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("fk_payments_checkout_session_id_checkout_sessions", type_="foreignkey")
        batch.drop_constraint("fk_payments_account_id_accounts", type_="foreignkey")
        batch.drop_index("ix_payments_checkout_session_id")
        batch.drop_index("ix_payments_account_id")
        batch.drop_column("checkout_session_id")
        batch.drop_column("account_id")
        batch.alter_column("user_id", existing_type=sa.BigInteger(), nullable=False)

    with op.batch_alter_table("designs") as batch:
        batch.drop_constraint("fk_designs_draft_id_design_drafts", type_="foreignkey")
        batch.drop_constraint("fk_designs_job_id_jobs", type_="foreignkey")
        batch.drop_constraint("fk_designs_account_id_accounts", type_="foreignkey")
        batch.drop_index("ix_designs_draft_id")
        batch.drop_index("ix_designs_job_id")
        batch.drop_index("ix_designs_account_id")
        batch.drop_column("draft_id")
        batch.drop_column("job_id")
        batch.drop_column("account_id")

    op.drop_index(op.f("ix_account_flow_events_created_at"), table_name="account_flow_events")
    op.drop_index(op.f("ix_account_flow_events_source"), table_name="account_flow_events")
    op.drop_index(op.f("ix_account_flow_events_action_key"), table_name="account_flow_events")
    op.drop_index(op.f("ix_account_flow_events_screen_key"), table_name="account_flow_events")
    op.drop_index(op.f("ix_account_flow_events_event_type"), table_name="account_flow_events")
    op.drop_index(op.f("ix_account_flow_events_account_id"), table_name="account_flow_events")
    op.drop_table("account_flow_events")

    op.drop_index(op.f("ix_checkout_sessions_provider_checkout_id"), table_name="checkout_sessions")
    op.drop_index(op.f("ix_checkout_sessions_status"), table_name="checkout_sessions")
    op.drop_index(op.f("ix_checkout_sessions_provider"), table_name="checkout_sessions")
    op.drop_index(op.f("ix_checkout_sessions_account_id"), table_name="checkout_sessions")
    op.drop_table("checkout_sessions")

    op.drop_index(op.f("ix_jobs_error_code"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_result_ref_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_draft_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_job_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_account_id"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_index(
        op.f("ix_furniture_search_drafts_status"), table_name="furniture_search_drafts"
    )
    op.drop_index(
        op.f("ix_furniture_search_drafts_account_id"),
        table_name="furniture_search_drafts",
    )
    op.drop_table("furniture_search_drafts")

    op.drop_index(op.f("ix_design_drafts_status"), table_name="design_drafts")
    op.drop_index(op.f("ix_design_drafts_account_id"), table_name="design_drafts")
    op.drop_table("design_drafts")

    op.drop_index(op.f("ix_account_sessions_status"), table_name="account_sessions")
    op.drop_index(
        op.f("ix_account_sessions_session_token_hash"), table_name="account_sessions"
    )
    op.drop_index(op.f("ix_account_sessions_account_id"), table_name="account_sessions")
    op.drop_table("account_sessions")

    op.drop_index(
        op.f("ix_account_identities_provider_email"), table_name="account_identities"
    )
    op.drop_index(op.f("ix_account_identities_provider"), table_name="account_identities")
    op.drop_index(op.f("ix_account_identities_account_id"), table_name="account_identities")
    op.drop_table("account_identities")

    op.drop_index(op.f("ix_accounts_primary_email"), table_name="accounts")
    op.drop_index(op.f("ix_accounts_status"), table_name="accounts")
    op.drop_table("accounts")
