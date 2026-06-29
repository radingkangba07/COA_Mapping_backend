"""006_project_selection_tables

Creates project_master_data_selections and project_opening_balance_selections.
Both tables cascade-delete when the parent project is removed.

Revision ID: 006
Revises: 005
Create Date: 2026-06-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_master_data_selections",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data_type", sa.String(100), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_project_master_data_project_id",
        "project_master_data_selections",
        ["project_id"],
    )

    op.create_table(
        "project_opening_balance_selections",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_type", sa.String(100), nullable=False),
        sa.Column("include", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_project_opening_balance_project_id",
        "project_opening_balance_selections",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_opening_balance_project_id", table_name="project_opening_balance_selections")
    op.drop_table("project_opening_balance_selections")
    op.drop_index("ix_project_master_data_project_id", table_name="project_master_data_selections")
    op.drop_table("project_master_data_selections")
