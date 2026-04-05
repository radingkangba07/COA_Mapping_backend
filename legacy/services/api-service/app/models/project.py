"""Project model for COA Migration."""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProjectStatus(str, Enum):
    """Status of a COA migration project."""
    DRAFT = "draft"              # Initial state, not started
    IN_PROGRESS = "in_progress"  # Work in progress
    PENDING_REVIEW = "pending_review"  # Waiting for approval
    COMPLETED = "completed"      # Finalized and exported


class Project(Base):
    """Project represents a COA migration session."""
    
    __tablename__ = "projects"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    # Link to company
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_erp: Mapped[str] = mapped_column(String(100), nullable=False)
    target_erp: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=ProjectStatus.DRAFT.value,
        index=True
    )
    # Creator tracking
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
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
    company = relationship("Company", back_populates="projects")
    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="project", cascade="all, delete-orphan")
    mappings = relationship("Mapping", back_populates="project", cascade="all, delete-orphan")
    access_list = relationship("ProjectAccess", back_populates="project", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name}, status={self.status})>"
