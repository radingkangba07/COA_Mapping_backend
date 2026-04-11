import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database import Base


class CoaMapping(Base):
    __tablename__ = "coa_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_account_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_account_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_account_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target_account_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_to_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="suggested")
    mapping_source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ai")
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    unique_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_coa_mappings_project_status", "project_id", "mapping_status"),
        Index("ix_coa_mappings_project_source_type", "project_id", "source_account_type"),
    )


class CoaMappingSuggestion(Base):
    __tablename__ = "coa_mappings_suggestion"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coa_mapping_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coa_mappings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_to_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_account_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_account_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_account_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target_account_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="suggested")
    mapping_source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="system")
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    unique_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_coa_suggestions_project_status", "project_id", "mapping_status"),)
