import uuid

from coa_db_models import Base
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class ProjectMasterDataSelection(Base):
    """One row per master-data type chosen for a project's migration scope."""

    __tablename__ = "project_master_data_selections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProjectOpeningBalanceSelection(Base):
    """One row per account-type included in the opening-balance migration."""

    __tablename__ = "project_opening_balance_selections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_type: Mapped[str] = mapped_column(String(100), nullable=False)
    include: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
