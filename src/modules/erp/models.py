import uuid

from coa_db_models import Base
from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class ErpCompatibilityRule(Base):
    __tablename__ = "erp_compatibility_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_product_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_product_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    connection_method_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_compatible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    incompatibility_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
