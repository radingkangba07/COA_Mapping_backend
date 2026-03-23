"""ProjectAccess model for user-project permissions."""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Permission(str, Enum):
    """Permission levels for project access."""
    VIEWER = "viewer"      # Can view project and mappings
    EDITOR = "editor"      # Can edit mappings
    APPROVER = "approver"  # Can approve/finalize mappings
    ADMIN = "admin"        # Full access including delete


class ProjectAccess(Base):
    """ProjectAccess represents user access to a project with permissions."""
    
    __tablename__ = "project_access"
    __table_args__ = (
        UniqueConstraint('user_id', 'project_id', name='uq_user_project'),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    permission: Mapped[str] = mapped_column(
        String(20),
        default=Permission.VIEWER.value,
        nullable=False
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    user = relationship("User", back_populates="project_access", foreign_keys=[user_id])
    project = relationship("Project", back_populates="access_list")
    
    def __repr__(self) -> str:
        return f"<ProjectAccess(user_id={self.user_id}, project_id={self.project_id}, permission={self.permission})>"
