"""Add upload intents, uploaded files, and draft file links.

Revision ID: d9e8f7a6b5c4
Revises: c1d2e3f4a5b6
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_uploaded_files_account_id"), "uploaded_files", ["account_id"], unique=False)
    op.create_index(op.f("ix_uploaded_files_purpose"), "uploaded_files", ["purpose"], unique=False)
    op.create_index(op.f("ix_uploaded_files_status"), "uploaded_files", ["status"], unique=False)

    op.create_table(
        "upload_intents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["file_id"], ["uploaded_files.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_upload_intents_account_id"), "upload_intents", ["account_id"], unique=False)
    op.create_index(op.f("ix_upload_intents_purpose"), "upload_intents", ["purpose"], unique=False)
    op.create_index(op.f("ix_upload_intents_status"), "upload_intents", ["status"], unique=False)
    op.create_index(op.f("ix_upload_intents_file_id"), "upload_intents", ["file_id"], unique=False)

    with op.batch_alter_table("design_drafts") as batch:
        batch.add_column(sa.Column("source_file_id", sa.UUID(), nullable=True))
        batch.add_column(sa.Column("style_reference_file_id", sa.UUID(), nullable=True))
        batch.create_index("ix_design_drafts_source_file_id", ["source_file_id"], unique=False)
        batch.create_index(
            "ix_design_drafts_style_reference_file_id", ["style_reference_file_id"], unique=False
        )
        batch.create_foreign_key(
            "fk_design_drafts_source_file_id_uploaded_files",
            "uploaded_files",
            ["source_file_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_design_drafts_style_reference_file_id_uploaded_files",
            "uploaded_files",
            ["style_reference_file_id"],
            ["id"],
        )

    with op.batch_alter_table("furniture_search_drafts") as batch:
        batch.add_column(sa.Column("source_file_id", sa.UUID(), nullable=True))
        batch.create_index(
            "ix_furniture_search_drafts_source_file_id", ["source_file_id"], unique=False
        )
        batch.create_foreign_key(
            "fk_furniture_search_drafts_source_file_id_uploaded_files",
            "uploaded_files",
            ["source_file_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("furniture_search_drafts") as batch:
        batch.drop_constraint(
            "fk_furniture_search_drafts_source_file_id_uploaded_files",
            type_="foreignkey",
        )
        batch.drop_index("ix_furniture_search_drafts_source_file_id")
        batch.drop_column("source_file_id")

    with op.batch_alter_table("design_drafts") as batch:
        batch.drop_constraint(
            "fk_design_drafts_style_reference_file_id_uploaded_files",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_design_drafts_source_file_id_uploaded_files",
            type_="foreignkey",
        )
        batch.drop_index("ix_design_drafts_style_reference_file_id")
        batch.drop_index("ix_design_drafts_source_file_id")
        batch.drop_column("style_reference_file_id")
        batch.drop_column("source_file_id")

    op.drop_index(op.f("ix_upload_intents_file_id"), table_name="upload_intents")
    op.drop_index(op.f("ix_upload_intents_status"), table_name="upload_intents")
    op.drop_index(op.f("ix_upload_intents_purpose"), table_name="upload_intents")
    op.drop_index(op.f("ix_upload_intents_account_id"), table_name="upload_intents")
    op.drop_table("upload_intents")

    op.drop_index(op.f("ix_uploaded_files_status"), table_name="uploaded_files")
    op.drop_index(op.f("ix_uploaded_files_purpose"), table_name="uploaded_files")
    op.drop_index(op.f("ix_uploaded_files_account_id"), table_name="uploaded_files")
    op.drop_table("uploaded_files")
