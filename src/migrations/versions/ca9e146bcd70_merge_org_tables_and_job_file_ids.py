"""merge org tables and job file ids

Revision ID: ca9e146bcd70
Revises: 01325dbd8a16, 80363d0e89b7
Create Date: 2026-04-10 07:03:37.493989

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "ca9e146bcd70"
down_revision: str | Sequence[str] | None = ("01325dbd8a16", "80363d0e89b7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
