"""Add mode/unit fields to designs and create design_projects table.

Revision ID: 9f2c7b8a1d4e
Revises: 8d4e7b2c1a9f
Create Date: 2026-02-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f2c7b8a1d4e"
down_revision: Union[str, Sequence[str], None] = "8d4e7b2c1a9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "design_projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processing"),
        sa.Column("rooms_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rooms_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rooms_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("units_spent_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_pdf_url", sa.String(length=1024), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_design_projects_user_id"), "design_projects", ["user_id"], unique=False)

    op.add_column(
        "designs",
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="full"),
    )
    op.add_column("designs", sa.Column("units_spent", sa.Integer(), nullable=True))
    op.add_column("designs", sa.Column("project_id", sa.UUID(), nullable=True))
    op.add_column("designs", sa.Column("room_index", sa.Integer(), nullable=True))
    op.add_column("designs", sa.Column("rooms_total", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_designs_project_id"), "designs", ["project_id"], unique=False)
    op.create_foreign_key(
        "fk_designs_project_id_design_projects",
        "designs",
        "design_projects",
        ["project_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_designs_project_id_design_projects", "designs", type_="foreignkey")
    op.drop_index(op.f("ix_designs_project_id"), table_name="designs")
    op.drop_column("designs", "rooms_total")
    op.drop_column("designs", "room_index")
    op.drop_column("designs", "project_id")
    op.drop_column("designs", "units_spent")
    op.drop_column("designs", "mode")

    op.drop_index(op.f("ix_design_projects_user_id"), table_name="design_projects")
    op.drop_table("design_projects")
