import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database import Base


class Mapping(Base):
    __tablename__ = "mappings"

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
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="suggested")
    remark: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ai")
    source_row_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_mappings_project_status", "project_id", "status"),
        Index("ix_mappings_project_source_type", "project_id", "source_account_type"),
    )
