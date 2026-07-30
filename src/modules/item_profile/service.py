import io
import logging
from datetime import UTC, datetime
from uuid import UUID

import pandas as pd
from coa_db_models.auth.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, PayloadTooLargeError, ValidationError
from src.modules.item_profile.publisher import ItemProfilePublisher
from src.modules.item_profile.repository import ItemProfileRunRepository
from src.modules.projects.dependencies import ensure_project_access
from src.modules.projects.repository import ProjectRepository
from src.modules.storage.s3_provider import S3Provider

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 500 * 1024 * 1024  # 500 MB
_TYPE_SAMPLE_ROWS = 500
_BOOL_STRINGS = {"true", "false", "1", "0", "yes", "no"}


def _infer_column_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "string"

    str_vals = non_null.astype(str)

    if all(v.lower() in _BOOL_STRINGS for v in str_vals):
        return "boolean"

    try:
        pd.to_numeric(non_null, errors="raise")
        # Distinguish integer vs decimal by checking for fractional parts
        as_float = non_null.astype(float)
        if (as_float == as_float.astype("int64")).all():
            return "integer"
        return "decimal"
    except (ValueError, TypeError):
        pass

    parsed_dates = pd.to_datetime(non_null, errors="coerce", format="mixed")
    if parsed_dates.notna().all():
        return "date"

    return "string"


def _parse_csv(raw: bytes) -> pd.DataFrame:
    """Attempt UTF-8 (with BOM), then Latin-1. Raises ValidationError on failure."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding, nrows=_TYPE_SAMPLE_ROWS)
            if df.columns.empty:
                raise ValidationError("CSV has no header row or columns could not be detected")
            return df
        except ValidationError:
            raise
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            raise ValidationError(f"CSV parsing failed: {exc}") from exc

    raise ValidationError("CSV encoding could not be determined; expected UTF-8 or Latin-1")


def _count_rows(raw: bytes) -> int:
    """Count data rows (excluding header) without loading the full file into pandas."""
    if not raw:
        return 0
    line_count = raw.count(b"\n")
    if not raw.endswith(b"\n"):
        line_count += 1
    return max(0, line_count - 1)


class ItemProfileService:
    def __init__(
        self,
        run_repo: ItemProfileRunRepository,
        store: S3Provider | None,
        publisher: ItemProfilePublisher | None,
        session: AsyncSession,
    ):
        self.run_repo = run_repo
        self.store = store
        self.publisher = publisher
        self.session = session

    async def initiate_run(self, project_id: UUID, source_file_ref: str, user: User) -> dict:
        """Validate inputs and create the run record synchronously. Returns {run_id, status}."""
        await ensure_project_access(self.session, user.id, project_id, "editor")

        project = await ProjectRepository(self.session).get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")

        if not self.store:
            raise ValidationError("Storage is not configured")

        if not self.store.object_exists(source_file_ref):
            raise ValidationError(f"File not found in storage: {source_file_ref}")

        size = self.store.get_object_size(source_file_ref)
        if size is not None and size > _MAX_FILE_BYTES:
            raise PayloadTooLargeError("File exceeds the 500 MB limit")

        run = await self.run_repo.create_run(
            project_id=project_id,
            started_at=datetime.now(UTC),
        )
        await self.session.commit()
        logger.info("Item profile run %s initiated for project %s", run.id, project_id)
        return {"run_id": run.id, "status": run.status}

    async def process_run(self, run_id: UUID, project_id: UUID, source_file_ref: str) -> None:
        """Background task: download, parse CSV, update run, publish NATS event."""
        try:
            assert self.store is not None
            raw, _ = self.store.get_object(source_file_ref)

            if len(raw) > _MAX_FILE_BYTES:
                raise PayloadTooLargeError("File exceeds the 500 MB limit")

            if len(raw) == 0:
                raise ValidationError("CSV file is empty")

            # Detect binary content — null bytes are present in all common binary formats
            # (PNG, PDF, XLSX, ZIP, etc.) but never in well-formed CSV text
            if b"\x00" in raw[:4096]:
                raise ValidationError("File does not appear to be a valid CSV (binary content detected)")

            sample_df = _parse_csv(raw)
            field_count = len(sample_df.columns)
            row_count = _count_rows(raw)

            await self.run_repo.update_run(
                run_id,
                status="profiling_pending",
                source_row_count=row_count,
                field_count=field_count,
                completed_at=datetime.now(UTC),
            )
            await self.session.commit()
            logger.info(
                "Run %s ingested: %d rows, %d fields — status=profiling_pending",
                run_id,
                row_count,
                field_count,
            )

            if self.publisher:
                await self.publisher.publish_run_created(run_id, project_id)

        except Exception as exc:
            error_msg = str(exc)
            logger.warning("Run %s ingestion failed: %s", run_id, error_msg)
            await self.run_repo.update_run(run_id, status="failed", error_detail=error_msg)
            await self.session.commit()
