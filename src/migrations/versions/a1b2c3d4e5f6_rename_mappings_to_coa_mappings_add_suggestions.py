"""rename mappings to coa_mappings and add coa_mappings_suggestion

Revision ID: a1b2c3d4e5f6
Revises: ebca09f2758e
Create Date: 2026-04-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "ebca09f2758e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Rename the existing mappings table to coa_mappings.
    op.rename_table("mappings", "coa_mappings")

    # 2. Rename existing indexes.
    op.execute("ALTER INDEX ix_mappings_project_id RENAME TO ix_coa_mappings_project_id")
    op.execute("ALTER INDEX ix_mappings_project_status RENAME TO ix_coa_mappings_project_status")
    op.execute("ALTER INDEX ix_mappings_project_source_type RENAME TO ix_coa_mappings_project_source_type")

    # 3. Rename status → mapping_status, remark → mapping_source, source_row_data → source_to_map.
    op.alter_column("coa_mappings", "status", new_column_name="mapping_status")
    op.alter_column("coa_mappings", "remark", new_column_name="mapping_source")
    op.alter_column("coa_mappings", "source_row_data", new_column_name="source_to_map")

    # 4. Add new columns from CSV coa_mappings spec.
    op.add_column("coa_mappings", sa.Column("source_row_id", sa.UUID(), nullable=True))
    op.add_column("coa_mappings", sa.Column("target_row_id", sa.UUID(), nullable=True))
    op.add_column("coa_mappings", sa.Column("unique_identifier", sa.String(length=255), nullable=True))
    op.add_column("coa_mappings", sa.Column("created_by", sa.UUID(), nullable=True))
    op.add_column("coa_mappings", sa.Column("updated_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_coa_mappings_created_by", "coa_mappings", "users", ["created_by"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_coa_mappings_updated_by", "coa_mappings", "users", ["updated_by"], ["id"], ondelete="SET NULL"
    )

    # 5. Change confidence_score type Float → Numeric(5, 2).
    op.alter_column(
        "coa_mappings",
        "confidence_score",
        type_=sa.Numeric(precision=5, scale=2),
        existing_type=sa.Float(),
        existing_server_default=sa.text("0.0"),
        server_default=sa.text("0"),
        postgresql_using="confidence_score::numeric(5,2)",
    )

    # 6. Create the new coa_mappings_suggestion table.
    op.create_table(
        "coa_mappings_suggestion",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("coa_mapping_id", sa.UUID(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("source_row_id", sa.UUID(), nullable=True),
        sa.Column("target_row_id", sa.UUID(), nullable=True),
        sa.Column("source_to_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_account_name", sa.String(length=500), nullable=True),
        sa.Column("source_account_type", sa.String(length=200), nullable=True),
        sa.Column("target_account_name", sa.String(length=500), nullable=True),
        sa.Column("target_account_type", sa.String(length=200), nullable=True),
        sa.Column("mapping_status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("mapping_source", sa.String(length=20), server_default="system", nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("unique_identifier", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["coa_mapping_id"], ["coa_mappings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_coa_mappings_suggestion_project_id"), "coa_mappings_suggestion", ["project_id"])
    op.create_index(op.f("ix_coa_mappings_suggestion_coa_mapping_id"), "coa_mappings_suggestion", ["coa_mapping_id"])
    op.create_index(op.f("ix_coa_mappings_suggestion_job_id"), "coa_mappings_suggestion", ["job_id"])
    op.create_index("ix_coa_suggestions_project_status", "coa_mappings_suggestion", ["project_id", "mapping_status"])


def downgrade() -> None:
    # 1. Drop coa_mappings_suggestion table and its indexes.
    op.drop_index("ix_coa_suggestions_project_status", table_name="coa_mappings_suggestion")
    op.drop_index(op.f("ix_coa_mappings_suggestion_job_id"), table_name="coa_mappings_suggestion")
    op.drop_index(op.f("ix_coa_mappings_suggestion_coa_mapping_id"), table_name="coa_mappings_suggestion")
    op.drop_index(op.f("ix_coa_mappings_suggestion_project_id"), table_name="coa_mappings_suggestion")
    op.drop_table("coa_mappings_suggestion")

    # 2. Revert confidence_score to Float.
    op.alter_column(
        "coa_mappings",
        "confidence_score",
        type_=sa.Float(),
        existing_type=sa.Numeric(precision=5, scale=2),
        existing_server_default=sa.text("0"),
        server_default=sa.text("0.0"),
        postgresql_using="confidence_score::double precision",
    )

    # 3. Drop FKs and added columns.
    op.drop_constraint("fk_coa_mappings_updated_by", "coa_mappings", type_="foreignkey")
    op.drop_constraint("fk_coa_mappings_created_by", "coa_mappings", type_="foreignkey")
    op.drop_column("coa_mappings", "updated_by")
    op.drop_column("coa_mappings", "created_by")
    op.drop_column("coa_mappings", "unique_identifier")
    op.drop_column("coa_mappings", "target_row_id")
    op.drop_column("coa_mappings", "source_row_id")

    # 4. Rename columns back.
    op.alter_column("coa_mappings", "source_to_map", new_column_name="source_row_data")
    op.alter_column("coa_mappings", "mapping_source", new_column_name="remark")
    op.alter_column("coa_mappings", "mapping_status", new_column_name="status")

    # 5. Restore old index names.
    op.execute("ALTER INDEX ix_coa_mappings_project_source_type RENAME TO ix_mappings_project_source_type")
    op.execute("ALTER INDEX ix_coa_mappings_project_status RENAME TO ix_mappings_project_status")
    op.execute("ALTER INDEX ix_coa_mappings_project_id RENAME TO ix_mappings_project_id")

    # 6. Rename table back.
    op.rename_table("coa_mappings", "mappings")
