"""008_project_wizard_fields

Stores ERP vendor and connection method fields for the project wizard that are
not yet part of the coa-db-models Project ORM model.

Revision ID: 008
Revises: 007
Create Date: 2026-06-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_wizard_fields",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_vendor_id", sa.String(100), nullable=True),
        sa.Column("target_vendor_id", sa.String(100), nullable=True),
        sa.Column("source_connection_method", sa.String(100), nullable=True),
        sa.Column("target_connection_method", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_wizard_fields_project_id",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("project_wizard_fields")
