"""007_erp_compatibility_rules

Creates erp_compatibility_rules table. Stores explicit compatibility overrides
between ERP product pairs and connection methods. Rows with a null
connection_method_id act as general fallback rules; rows with a specific
connection_method_id take precedence.

Revision ID: 007
Revises: 006
Create Date: 2026-06-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_compatibility_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_product_id", sa.String(100), nullable=False),
        sa.Column("target_product_id", sa.String(100), nullable=False),
        sa.Column("connection_method_id", sa.String(100), nullable=True),
        sa.Column("is_compatible", sa.Boolean(), nullable=False),
        sa.Column("incompatibility_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_compat_source", "erp_compatibility_rules", ["source_product_id"])
    op.create_index("ix_compat_target", "erp_compatibility_rules", ["target_product_id"])


def downgrade() -> None:
    op.drop_index("ix_compat_target", table_name="erp_compatibility_rules")
    op.drop_index("ix_compat_source", table_name="erp_compatibility_rules")
    op.drop_table("erp_compatibility_rules")
