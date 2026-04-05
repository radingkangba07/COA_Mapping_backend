"""File model for uploaded COA files with object storage support."""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FileType(str, Enum):
    """Type of uploaded file."""
    SOURCE_COA = "source_coa"
    TARGET_COA = "target_coa"
    TYPE_MAPPING = "type_mapping"
    UPLOAD = "upload"
    ARTIFACT = "artifact"
    EXPORT = "export"


class FileStatus(str, Enum):
    """Status of a file."""
    PENDING = "pending"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class File(Base):
    """File represents an uploaded file with object storage metadata."""
    
    __tablename__ = "files"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Ownership
    company_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # File metadata
    file_type: Mapped[str] = mapped_column(String(50), nullable=False, default=FileType.UPLOAD.value)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # Object storage
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True)
    storage_provider: Mapped[str] = mapped_column(String(50), default="emergent")
    etag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=FileStatus.PENDING.value,
        index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Parsed data (for COA files)
    columns: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    # Audit
    uploaded_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
    project = relationship("Project", back_populates="files")
    
    def __repr__(self) -> str:
        return f"<File(id={self.id}, type={self.file_type}, filename={self.original_filename})>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "company_id": self.company_id,
            "project_id": str(self.project_id),
            "job_id": str(self.job_id) if self.job_id else None,
            "file_type": self.file_type,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "storage_path": self.storage_path,
            "status": self.status,
            "columns": self.columns.get("columns", []) if self.columns else [],
            "row_count": self.row_count,
            "uploaded_by": self.uploaded_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
