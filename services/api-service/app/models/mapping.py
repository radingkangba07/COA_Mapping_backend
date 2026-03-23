"""Mapping model for COA account mappings."""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MappingStatus(str, Enum):
    """Status of a mapping."""
    SUGGESTED = "suggested"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class MappingRemark(str, Enum):
    """Source of the mapping."""
    AI = "ai"
    USER = "user"
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"


class Mapping(Base):
    """Mapping represents a source-to-target account mapping."""
    
    __tablename__ = "mappings"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Source account info
    source_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_account_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_account_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    
    # Target account info
    target_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_account_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target_account_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    
    # Mapping metadata
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(20),
        default=MappingStatus.SUGGESTED.value,
        index=True
    )
    remark: Mapped[str] = mapped_column(
        String(20),
        default=MappingRemark.AI.value
    )
    
    # Additional data
    source_row_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    project = relationship("Project", back_populates="mappings")
    
    def __repr__(self) -> str:
        return f"<Mapping(id={self.id}, source={self.source_account_name}, target={self.target_account_name})>"
