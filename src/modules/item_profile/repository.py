from datetime import datetime
from uuid import UUID

from coa_db_models.profiling.models import (
    ItemFieldProfile,
    ItemProfileAudit,
    ItemProfileDecision,
    ItemProfileRun,
)
from sqlalchemy import Float, Integer, and_, case, delete, func, insert, or_, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError


class ItemProfileRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, project_id: UUID, started_at: datetime, source_file_ref: str) -> ItemProfileRun:
        run = ItemProfileRun(
            project_id=project_id,
            status="ingesting",
            started_at=started_at,
            source_file_ref=source_file_ref,
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def update_run(
        self,
        run_id: UUID,
        *,
        status: str,
        source_row_count: int | None = None,
        field_count: int | None = None,
        fields_processed: int | None = None,
        error_detail: str | None = None,
        completed_at: datetime | None = None,
        duplicate_summary: dict | None = None,
        cross_subsidiary_summary: dict | None = None,
        invalid_uom_count: int | None = None,
        missing_product_type_count: int | None = None,
        interpretation_text: str | None = None,
        recommended_actions: dict | None = None,
    ) -> None:
        run = await self.session.get(ItemProfileRun, run_id)
        if not run:
            return
        run.status = status
        if source_row_count is not None:
            run.source_row_count = source_row_count
        if field_count is not None:
            run.field_count = field_count
        if fields_processed is not None:
            run.fields_processed = fields_processed
        if error_detail is not None:
            run.error_detail = error_detail
        if completed_at is not None:
            run.completed_at = completed_at
        if duplicate_summary is not None:
            run.duplicate_summary = duplicate_summary
        if cross_subsidiary_summary is not None:
            run.cross_subsidiary_summary = cross_subsidiary_summary
        if invalid_uom_count is not None:
            run.invalid_uom_count = invalid_uom_count
        if missing_product_type_count is not None:
            run.missing_product_type_count = missing_product_type_count
        if interpretation_text is not None:
            run.interpretation_text = interpretation_text
        if recommended_actions is not None:
            run.recommended_actions = recommended_actions
        await self.session.flush()

    async def list_runs(self, project_id: UUID) -> list[ItemProfileRun]:
        result = await self.session.execute(
            select(ItemProfileRun)
            .where(ItemProfileRun.project_id == project_id)
            .order_by(ItemProfileRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_run(self, run_id: UUID) -> ItemProfileRun | None:
        return await self.session.get(ItemProfileRun, run_id)

    async def get_run_or_404(self, run_id: UUID) -> ItemProfileRun:
        run = await self.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")
        return run


class ItemFieldProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_by_run(self, run_id: UUID) -> None:
        await self.session.execute(
            delete(ItemFieldProfile).where(ItemFieldProfile.run_id == run_id)
        )
        await self.session.flush()

    async def bulk_create(self, profiles: list[dict]) -> None:
        if not profiles:
            return
        await self.session.execute(insert(ItemFieldProfile), profiles)
        await self.session.flush()

    _FINDING_TYPE_CONDITIONS = {
        "blocker": lambda: ItemFieldProfile.severity == "blocker",
        "identifier_candidate": lambda: ItemFieldProfile.semantic_role.in_(
            ["identifier_candidate", "cross_subsidiary_identifier"]
        ),
        "value_list": lambda: ItemFieldProfile.semantic_role == "value_list",
        "pattern_anomaly": lambda: and_(
            ItemFieldProfile.anomaly_count.isnot(None), ItemFieldProfile.anomaly_count > 0
        ),
        "missing_values": lambda: and_(
            ItemFieldProfile.null_count > 0, ItemFieldProfile.null_count < ItemFieldProfile.total_count
        ),
        "near_empty": lambda: sa_cast(ItemFieldProfile.stats["null_pct"].astext, Float) > 80,
        "duplicate": lambda: sa_cast(
            ItemFieldProfile.stats["duplicate_row_count"].astext, Integer
        ) > 0,
        "reference_failure": lambda: and_(
            ItemFieldProfile.semantic_role.in_(["identifier_candidate", "cross_subsidiary_identifier"]),
            ItemFieldProfile.null_count > 0,
        ),
    }

    async def get_finding_type_counts(self, run_id: UUID) -> dict:
        dup_col = sa_cast(ItemFieldProfile.stats["duplicate_row_count"].astext, Integer)
        result = await self.session.execute(
            select(
                func.count().label("all_fields"),
                func.sum(case((ItemFieldProfile.severity == "blocker", 1), else_=0)).label("blockers"),
                func.sum(case((
                    ItemFieldProfile.semantic_role.in_(["identifier_candidate", "cross_subsidiary_identifier"]),
                    1), else_=0)).label("identifier_candidates"),
                func.sum(case((ItemFieldProfile.semantic_role == "value_list", 1), else_=0)).label("value_list_detected"),
                func.sum(case((
                    and_(ItemFieldProfile.anomaly_count.isnot(None), ItemFieldProfile.anomaly_count > 0),
                    1), else_=0)).label("pattern_anomalies"),
                func.sum(case((
                    and_(ItemFieldProfile.null_count > 0, ItemFieldProfile.null_count < ItemFieldProfile.total_count),
                    1), else_=0)).label("missing_values"),
                func.sum(case((
                    sa_cast(ItemFieldProfile.stats["null_pct"].astext, Float) > 80,
                    1), else_=0)).label("near_empty"),
                func.sum(case((dup_col > 0, 1), else_=0)).label("duplicates"),
                func.sum(case((
                    and_(
                        ItemFieldProfile.semantic_role.in_(["identifier_candidate", "cross_subsidiary_identifier"]),
                        ItemFieldProfile.null_count > 0,
                    ),
                    1), else_=0)).label("reference_failures"),
            ).where(ItemFieldProfile.run_id == run_id)
        )
        row = result.one()
        return {
            "all_fields": row.all_fields or 0,
            "blockers": row.blockers or 0,
            "identifier_candidates": row.identifier_candidates or 0,
            "duplicates": row.duplicates or 0,
            "missing_values": row.missing_values or 0,
            "invalid_values": 0,
            "near_empty": row.near_empty or 0,
            "outliers": 0,
            "value_list_detected": row.value_list_detected or 0,
            "reference_failures": row.reference_failures or 0,
            "pattern_anomalies": row.pattern_anomalies or 0,
        }

    async def list_fields(
        self,
        run_id: UUID,
        *,
        role: str | None = None,
        severity: str | None = None,
        finding_type: str | None = None,
        search: str | None = None,
        sort: str = "field_name",
        order: str = "asc",
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[ItemFieldProfile], int]:
        query = select(ItemFieldProfile).where(ItemFieldProfile.run_id == run_id)
        if role:
            query = query.where(ItemFieldProfile.semantic_role == role)
        if severity:
            query = query.where(ItemFieldProfile.severity == severity)
        if finding_type and finding_type in self._FINDING_TYPE_CONDITIONS:
            query = query.where(self._FINDING_TYPE_CONDITIONS[finding_type]())
        if search:
            query = query.where(ItemFieldProfile.field_name.ilike(f"%{search}%"))

        _sort_cols = {
            "uniqueness_pct": sa_cast(ItemFieldProfile.stats["uniqueness_pct"].astext, Float),
            "null_pct": sa_cast(ItemFieldProfile.stats["null_pct"].astext, Float),
            "field_name": ItemFieldProfile.field_name,
        }
        sort_col = _sort_cols.get(sort, ItemFieldProfile.field_name)
        query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

        count_result = await self.session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        paged = await self.session.execute(query.offset(offset).limit(page_size))
        return list(paged.scalars().all()), total

    async def get_field(self, run_id: UUID, field_name: str) -> ItemFieldProfile | None:
        result = await self.session.execute(
            select(ItemFieldProfile).where(
                ItemFieldProfile.run_id == run_id,
                ItemFieldProfile.field_name == field_name,
            )
        )
        return result.scalar_one_or_none()

    async def get_field_or_404(self, run_id: UUID, field_name: str) -> ItemFieldProfile:
        fp = await self.get_field(run_id, field_name)
        if fp is None:
            raise NotFoundError(f"Field '{field_name}' not found in run {run_id}")
        return fp

    async def compute_coverage(self, run_id: UUID) -> dict:
        result = await self.session.execute(
            select(
                func.count(ItemFieldProfile.id).label("total_fields"),
                func.sum(ItemFieldProfile.null_count).label("total_nulls"),
                func.sum(ItemFieldProfile.total_count).label("total_values"),
                func.avg(
                    sa_cast(ItemFieldProfile.distinct_count, Float)
                    / func.nullif(ItemFieldProfile.total_count - ItemFieldProfile.null_count, 0)
                    * 100
                ).label("avg_uniqueness"),
                func.sum(
                    case(
                        (
                            or_(
                                ItemFieldProfile.anomaly_count.is_(None),
                                ItemFieldProfile.anomaly_count == 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("conforming_fields"),
            ).where(ItemFieldProfile.run_id == run_id)
        )
        row = result.one()
        if not row.total_fields:
            return {"completeness_pct": None, "uniqueness_pct": None, "pattern_conformance_pct": None}
        total_values = row.total_values or 0
        total_nulls = row.total_nulls or 0
        completeness = round(100.0 * (1 - total_nulls / total_values), 1) if total_values else 100.0
        uniqueness = round(float(row.avg_uniqueness), 1) if row.avg_uniqueness is not None else None
        conformance = round(100.0 * (row.conforming_fields or 0) / row.total_fields, 1)
        return {
            "completeness_pct": completeness,
            "uniqueness_pct": uniqueness,
            "pattern_conformance_pct": conformance,
        }


class ItemProfileDecisionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_pending(self, run_id: UUID, field_name: str) -> ItemProfileDecision | None:
        result = await self.session.execute(
            select(ItemProfileDecision).where(
                ItemProfileDecision.run_id == run_id,
                ItemProfileDecision.field_name == field_name,
                ItemProfileDecision.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def create_decision(
        self,
        run_id: UUID,
        field_name: str,
        decision_type: str,
        fix_type: str | None,
        fix_params: dict | None,
        user_id: UUID,
    ) -> ItemProfileDecision:
        existing = await self.get_pending(run_id, field_name)
        if existing and existing.action == decision_type:
            raise ConflictError(
                f"A pending '{decision_type}' decision already exists for field '{field_name}'"
            )
        if existing:
            raise ConflictError(
                f"Field '{field_name}' already has a pending decision; undo it before creating a new one"
            )

        decision = ItemProfileDecision(
            run_id=run_id,
            field_name=field_name,
            action=decision_type,
            fix_type=fix_type,
            transformation_config=fix_params,
            status="pending",
            decided_by=user_id,
        )
        self.session.add(decision)
        await self.session.flush()
        await self.session.refresh(decision)

        audit = ItemProfileAudit(
            decision_id=decision.id,
            changed_by=user_id,
            previous_state=None,
            new_state={
                "action": decision_type,
                "fix_type": fix_type,
                "fix_params": fix_params,
                "status": "pending",
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return decision

    async def list_decisions(self, run_id: UUID) -> list[ItemProfileDecision]:
        result = await self.session.execute(
            select(ItemProfileDecision)
            .where(ItemProfileDecision.run_id == run_id)
            .order_by(ItemProfileDecision.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_decision_or_404(self, decision_id: UUID) -> ItemProfileDecision:
        decision = await self.session.get(ItemProfileDecision, decision_id)
        if decision is None:
            raise NotFoundError(f"Decision {decision_id} not found")
        return decision

    async def undo_decision(
        self,
        decision_id: UUID,
        user_id: UUID,
        field_repo: "ItemFieldProfileRepository | None" = None,
    ) -> ItemProfileDecision:
        decision = await self.get_decision_or_404(decision_id)
        if decision.status == "undone":
            raise ConflictError("Decision is already undone")

        if decision.status == "applied" and field_repo is not None:
            await self._reverse_applied_fix(decision, user_id, field_repo)

        previous_state = {
            "action": decision.action,
            "fix_type": decision.fix_type,
            "fix_params": decision.transformation_config,
            "status": decision.status,
        }
        decision.status = "undone"
        await self.session.flush()

        audit = ItemProfileAudit(
            decision_id=decision.id,
            changed_by=user_id,
            previous_state=previous_state,
            new_state={**previous_state, "status": "undone"},
        )
        self.session.add(audit)
        await self.session.flush()
        return decision

    async def _reverse_applied_fix(
        self,
        decision: ItemProfileDecision,
        user_id: UUID,
        field_repo: "ItemFieldProfileRepository",
    ) -> None:
        """Restore field stats to pre-fix state using the stored audit previous_state."""
        result = await self.session.execute(
            select(ItemProfileAudit)
            .where(ItemProfileAudit.decision_id == decision.id)
            .where(ItemProfileAudit.new_state["action"].astext == "fix_applied")
            .order_by(ItemProfileAudit.changed_at.desc())
            .limit(1)
        )
        apply_audit = result.scalar_one_or_none()
        if apply_audit is None or apply_audit.previous_state is None:
            return

        fp = await field_repo.get_field(decision.run_id, decision.field_name)
        if fp is None:
            return

        prev = apply_audit.previous_state
        fp.stats = prev.get("stats")
        if prev.get("distinct_count") is not None:
            fp.distinct_count = prev["distinct_count"]
        await self.session.flush()

    async def execute_fix(
        self,
        decision_id: UUID,
        user_id: UUID,
        field_repo: "ItemFieldProfileRepository",
    ) -> tuple[ItemProfileDecision, int]:
        """Execute an approved apply_fix decision. Idempotent — safe to call twice."""
        from src.modules.item_profile.fix_engine import apply_fix

        decision = await self.get_decision_or_404(decision_id)

        if decision.status == "applied":
            result = await self.session.execute(
                select(ItemProfileAudit)
                .where(ItemProfileAudit.decision_id == decision_id)
                .where(ItemProfileAudit.new_state["action"].astext == "fix_applied")
                .order_by(ItemProfileAudit.changed_at.desc())
                .limit(1)
            )
            apply_audit = result.scalar_one_or_none()
            rows_affected = (apply_audit.new_state or {}).get("rows_affected", 0) if apply_audit else 0
            return decision, rows_affected

        if decision.status != "pending":
            raise ConflictError(f"Cannot execute a decision with status '{decision.status}'")
        if decision.action != "apply_fix":
            raise ConflictError("Only apply_fix decisions can be executed")

        fp = await field_repo.get_field_or_404(decision.run_id, decision.field_name)
        stats = fp.stats or {}
        top_values = stats.get("top_values") or []

        new_top_values, rows_affected, change_log = apply_fix(
            top_values,
            decision.fix_type or "",
            decision.transformation_config,
        )

        previous_state = {"stats": fp.stats, "distinct_count": fp.distinct_count}

        new_stats = {**stats, "top_values": new_top_values}
        fp.stats = new_stats
        fp.distinct_count = len(new_top_values)
        await self.session.flush()

        decision.status = "applied"
        await self.session.flush()

        audit = ItemProfileAudit(
            decision_id=decision_id,
            changed_by=user_id,
            previous_state=previous_state,
            new_state={
                "action": "fix_applied",
                "fix_type": decision.fix_type,
                "field_name": decision.field_name,
                "rows_affected": rows_affected,
                "changes": change_log,
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return decision, rows_affected

    async def list_project_decisions(self, project_id: UUID) -> list[ItemProfileDecision]:
        result = await self.session.execute(
            select(ItemProfileDecision)
            .join(ItemProfileRun, ItemProfileDecision.run_id == ItemProfileRun.id)
            .where(
                ItemProfileRun.project_id == project_id,
                ItemProfileDecision.status == "pending",
                ItemProfileDecision.action.in_(["confirm_identifier", "apply_fix"]),
            )
            .order_by(ItemProfileDecision.created_at.desc())
        )
        return list(result.scalars().all())

    async def execute_confirm_identifier(
        self,
        decision_id: UUID,
        user_id: UUID,
        run_repo: "ItemProfileRunRepository",
    ) -> ItemProfileDecision:
        """Set the run migration key field. Idempotent — safe to call twice."""
        decision = await self.get_decision_or_404(decision_id)

        if decision.status == "applied":
            return decision

        if decision.status != "pending":
            raise ConflictError(f"Cannot execute a decision with status '{decision.status}'")
        if decision.action != "confirm_identifier":
            raise ConflictError("Only confirm_identifier decisions can be executed here")

        run = await run_repo.get_run_or_404(decision.run_id)
        previous_migration_key = run.migration_key_field

        run.migration_key_field = decision.field_name
        await self.session.flush()

        decision.status = "applied"
        await self.session.flush()

        audit = ItemProfileAudit(
            decision_id=decision.id,
            changed_by=user_id,
            previous_state={"migration_key_field": previous_migration_key},
            new_state={
                "action": "identifier_confirmed",
                "field_name": decision.field_name,
                "migration_key_field": decision.field_name,
            },
        )
        self.session.add(audit)
        await self.session.flush()
        return decision

    async def get_pending_apply_fix(self, run_id: UUID, field_name: str) -> ItemProfileDecision | None:
        result = await self.session.execute(
            select(ItemProfileDecision).where(
                ItemProfileDecision.run_id == run_id,
                ItemProfileDecision.field_name == field_name,
                ItemProfileDecision.action == "apply_fix",
                ItemProfileDecision.status == "pending",
            )
        )
        return result.scalar_one_or_none()
