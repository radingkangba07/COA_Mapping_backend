import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from coa_db_models.profiling.models import ItemProfileRun
from nats.js import JetStreamContext

from src.core.config import get_settings
from src.modules.item_profile.repository import ItemFieldProfileRepository, ItemProfileRunRepository
from src.core.config import get_settings
from src.modules.item_profile.service import (
    apply_semantic_roles,
    compute_all_stats,
    compute_field_findings,
    compute_migration_impact,
    detect_cross_subsidiary_splits,
    detect_duplicates,
    detect_uom_issues,
    detect_missing_product_type,
    load_full_csv,
    _count_rows,
)
from src.modules.item_profile.odoo_mapper import classify_odoo_target
from src.modules.storage.s3_provider import S3Provider

logger = logging.getLogger(__name__)

# Statuses that indicate the run is already terminal — skip on duplicate event.
_TERMINAL_STATUSES = frozenset(["complete", "failed"])

# Staged pipeline status labels.
_STATUS_STATISTICS = "profiling_statistics"
_STATUS_PATTERNS = "profiling_patterns"
_STATUS_ROLES = "profiling_roles"
_STATUS_COMPLETE = "complete"
_STATUS_FAILED = "failed"


class ItemProfileConsumer:
    def __init__(
        self,
        jetstream: JetStreamContext,
        run_repo: ItemProfileRunRepository,
        field_repo: ItemFieldProfileRepository,
        store: S3Provider | None,
        session,
    ):
        self.js = jetstream
        self.run_repo = run_repo
        self.field_repo = field_repo
        self.store = store
        self.session = session
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        settings = get_settings()
        subject = settings.nats_subject_item_profile_run_created
        durable = settings.nats_durable_item_profile
        try:
            self.sub = await self.js.subscribe(subject, durable=durable, manual_ack=True)
        except Exception:
            logger.warning("Durable consumer %s already bound, recreating", durable)
            try:
                await self.js.delete_consumer(settings.nats_stream_name, durable)
            except Exception:
                pass
            self.sub = await self.js.subscribe(subject, durable=durable, manual_ack=True)
        self._task = asyncio.create_task(self._consume())
        logger.info("Item profile consumer started, listening on %s", subject)

    async def stop(self) -> None:
        logger.info("Stopping item profile consumer")
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Item profile consumer task raised during shutdown")
            self._task = None
        sub = getattr(self, "sub", None)
        if sub is not None:
            try:
                await sub.unsubscribe()
            except Exception:
                logger.exception("Failed to unsubscribe item profile consumer")
        if self.session is not None:
            try:
                await self.session.close()
            except Exception:
                logger.exception("Failed to close item profile consumer DB session")
        logger.info("Item profile consumer stopped")

    async def _consume(self) -> None:
        async for msg in self.sub.messages:
            try:
                data = json.loads(msg.data.decode())
                await self._handle_run_created(data)
                await msg.ack()
            except Exception:
                logger.exception("Failed to process item-profile.run.created message")
                await msg.nak(delay=5)

    async def _handle_run_created(self, data: dict) -> None:
        run_id = UUID(data["run_id"])

        run: ItemProfileRun | None = await self.session.get(ItemProfileRun, run_id)
        if run is None:
            logger.warning("Run %s not found, skipping", run_id)
            return

        # Idempotency: duplicate events for already-terminal runs are silently skipped.
        if run.status in _TERMINAL_STATUSES:
            logger.info("Run %s already %s, skipping duplicate event", run_id, run.status)
            return

        if not run.source_file_ref:
            logger.warning("Run %s has no source_file_ref, skipping", run_id)
            return

        try:
            if not self.store:
                raise RuntimeError("Storage not configured")

            settings = get_settings()

            # ----------------------------------------------------------------
            # Stage 1: Field statistics
            # ----------------------------------------------------------------
            raw, _ = self.store.get_object(run.source_file_ref)
            df = load_full_csv(raw)
            field_count = len(df.columns)
            row_count = _count_rows(raw)

            await self.run_repo.update_run(
                run_id,
                status=_STATUS_STATISTICS,
                source_row_count=row_count,
                field_count=field_count,
                fields_processed=0,
            )
            await self.session.commit()
            logger.info("Run %s stage 1/3: computing field statistics (%d fields)", run_id, field_count)

            all_stats = compute_all_stats(df)

            # ----------------------------------------------------------------
            # Stage 2: Pattern and anomaly + duplicate/cross-subsidiary detection
            # ----------------------------------------------------------------
            await self.run_repo.update_run(
                run_id,
                status=_STATUS_PATTERNS,
                fields_processed=len(all_stats),
            )
            await self.session.commit()
            logger.info("Run %s stage 2/3: detecting patterns and duplicates", run_id)

            dup_summary = detect_duplicates(df)
            cross_sub_summary = detect_cross_subsidiary_splits(df)

            # ----------------------------------------------------------------
            # Stage 3: Semantic role inference
            # ----------------------------------------------------------------
            await self.run_repo.update_run(run_id, status=_STATUS_ROLES)
            await self.session.commit()
            logger.info("Run %s stage 3/3: inferring semantic roles", run_id)

            apply_semantic_roles(
                all_stats,
                cross_sub_summary,
                settings.profile_identifier_min_uniqueness,
                settings.profile_identifier_max_null_pct,
            )

            # ----------------------------------------------------------------
            # Persist field profiles and mark complete
            # ----------------------------------------------------------------
            invalid_uom_count = detect_uom_issues(df, all_stats)
            missing_product_type_count = detect_missing_product_type(df, all_stats)

            await self.field_repo.delete_by_run(run_id)
            await self.field_repo.bulk_create([
                {
                    "run_id": run_id,
                    "field_name": s.field_name,
                    "detected_type": s.detected_type,
                    "total_count": s.total_count,
                    "null_count": s.null_count,
                    "distinct_count": s.distinct_count,
                    "severity": s.severity,
                    "cardinality": s.cardinality,
                    "pattern_summary": s.pattern_summary,
                    "anomaly_count": s.anomaly_count,
                    "anomaly_examples": s.anomaly_examples or None,
                    "semantic_role": s.semantic_role,
                    "confidence_score": s.confidence_score,
                    "evidence": s.evidence or None,
                    "sample_values": [v["value"] for v in s.top_values[:3]] if s.top_values else None,
                    "odoo_target": classify_odoo_target(
                        s.semantic_role,
                        s.detected_type,
                        s.pattern_summary,
                    ),
                    "stats": {
                        "null_pct": s.null_pct,
                        "uniqueness_pct": s.uniqueness_pct,
                        "top_values": s.top_values,
                        "text_len_min": s.text_len_min,
                        "text_len_max": s.text_len_max,
                        "text_len_mean": s.text_len_mean,
                        "numeric_min": s.numeric_min,
                        "numeric_max": s.numeric_max,
                        "numeric_mean": s.numeric_mean,
                        "numeric_std": s.numeric_std,
                        "duplicate_row_count": s.duplicate_row_count,
                        "duplicate_group_count": s.duplicate_group_count,
                    },
                }
                for s in all_stats
            ])

            await self.run_repo.update_run(
                run_id,
                status=_STATUS_COMPLETE,
                completed_at=datetime.now(UTC),
                fields_processed=len(all_stats),
                duplicate_summary=dup_summary,
                cross_subsidiary_summary=cross_sub_summary,
                invalid_uom_count=invalid_uom_count,
                missing_product_type_count=missing_product_type_count,
            )
            await self.session.commit()
            logger.info(
                "Run %s complete: %d fields profiled from %d rows",
                run_id, len(all_stats), row_count,
            )

        except Exception as exc:
            logger.exception("Field profiling failed for run %s", run_id)
            await self.run_repo.update_run(run_id, status=_STATUS_FAILED, error_detail=str(exc))
            await self.session.commit()
            raise
