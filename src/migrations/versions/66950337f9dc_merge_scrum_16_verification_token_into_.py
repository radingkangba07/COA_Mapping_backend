"""merge SCRUM-16 verification token into mappingservice integration

Revision ID: 66950337f9dc
Revises: ca9e146bcd70, f59248742306
Create Date: 2026-04-11 11:40:40.232000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "66950337f9dc"
down_revision: str | Sequence[str] | None = ("ca9e146bcd70", "f59248742306")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
