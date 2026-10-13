"""Governed run commands, separate acceptance, bounded reads and async execution.

Only this aggregate is written. Foundation, estimates, P6, FIN and Gate sources
are revalidated through the existing read-only Foundation authority.
"""

from copy import deepcopy
from datetime import timedelta
from secrets import randbits
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm.exc import StaleDataError

from app.api.v1.routers.admin_configuration import _workspace_path
from app.core.time import utc_now
from app.domain.models import (
    AdminNumberSequence,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    UserAccount,
)
from app.modules.basic_data.service import _hash, _json
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.qra_engine.models import QraRun, QraRunReview
from app.modules.qra_foundation.models import QraModelDefinition
from app.modules.qra_foundation.service import QraFoundationService

ENGINE_VERSION = "wave4-qra-v1"
FORMULA_VERSION = "distribution-inverse-cdf-v1"
PROVIDER_KEY = "QRA_RESULT_PROVIDER"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
PERMISSIONS = {action: f"qra_run.{action}" for action in ("read", "create", "execute", "cancel", "review", "accept")}
_UNSET_REVIEW = object()


def audit_denial(db, tenant_id, actor_id, code, *, target_id=None):
    """Denials survive the failed command rollback; never retain supplied payloads."""
    db.rollback()
    if db.scalar(select(UserAccount.id).where(UserAccount.id == actor_id, UserAccount.tenant_id == tenant_id)):
        db.add(
            SecurityEvent(
                tenant_id=tenant_id,
                user_id=actor_id,
                event_type="qra.run.denied",
                outcome="denied",
                target_type="QraRun",
                target_id=target_id,
                metadata_json={"code": str(code)[:240]},
            )
        )
        db.commit()


def _code(exc):
    return exc.detail.get("code", "QRA_RUN_DENIED") if isinstance(exc.detail, dict) else str(exc.detail)


class QraEngineService(QraFoundationService):
    def __init__(self, db, tenant_id, actor_id, context=None, dispatcher=None):
        super().__init__(db, tenant_id, actor_id, context)
        self.dispatcher = dispatcher

    def _permission(self, action, project_id):
        # Direct service tests/trusted calls may omit context. HTTP and worker
        # always pass a real context, and each action gets its own scoped grant.
        if self.context is not None:
            context = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, PERMISSIONS[action], bootstrap=False
            )
            scoped = QraFoundationService(self.db, self.tenant_id, self.actor_id, context)
            scoped._project(project_id)
        else:
            self._project(project_id)

    def _allowed(self, project_id):
        if self.context is None:
            return []
        project = self._project(project_id)
        path = {w.id for w in _workspace_path(self.db, self.tenant_id, project)}
        group_ids = self.db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == self.tenant_id, SecurityGroupMember.user_id == self.actor_id
            )
        ).all()
        now = utc_now()
        # A single permission projection, equivalent to the existing Enterprise
        # grant resolver, rather than six repeated actor/group/role scans.
        keys = set(
            self.db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .join(SecurityRole, SecurityRole.id == SecurityRolePermission.role_id)
                .join(SecurityAccessAssignment, SecurityAccessAssignment.role_id == SecurityRole.id)
                .where(
                    PermissionCatalog.status == "active",
                    SecurityRole.tenant_id == self.tenant_id,
                    SecurityRole.status == "active",
                    SecurityRolePermission.tenant_id == self.tenant_id,
                    SecurityAccessAssignment.tenant_id == self.tenant_id,
                    SecurityAccessAssignment.status == "active",
                    (SecurityAccessAssignment.user_id == self.actor_id)
                    | SecurityAccessAssignment.group_id.in_(group_ids or [-1]),
                    SecurityAccessAssignment.starts_at.is_(None) | (SecurityAccessAssignment.starts_at <= now),
                    SecurityAccessAssignment.ends_at.is_(None) | (SecurityAccessAssignment.ends_at > now),
                    (SecurityAccessAssignment.scope_type == "organization")
                    | SecurityAccessAssignment.workspace_id.in_(path),
                    PermissionCatalog.key.in_(list(PERMISSIONS.values())),
                )
            )
        )
        return [action for action, permission in PERMISSIONS.items() if permission in keys]

    def _run(self, run_id, *, lock=False):
        query = select(QraRun).where(QraRun.tenant_id == self.tenant_id, QraRun.id == run_id)
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "QRA_RUN_NOT_FOUND")
        self._project(row.project_workspace_id)
        return row

    def _review(self, run_id, *, lock=False):
        query = select(QraRunReview).where(QraRunReview.tenant_id == self.tenant_id, QraRunReview.run_id == run_id)
        return self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)

    def _revision(self, row, review=_UNSET_REVIEW):
        if review is _UNSET_REVIEW:
            review = self._review(row.id)
        return row.revision_version + (review.revision_version if review else 0)

    def _run_out(self, row, *, include_results=False, review=_UNSET_REVIEW, allowed=None):
        if review is _UNSET_REVIEW:
            review = self._review(row.id)
        result = _json(
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "run_number",
                    "model_number",
                    "model_version",
                    "model_hash",
                    "analysis_type",
                    "engine_name",
                    "engine_version",
                    "formula_version",
                    "configuration_id",
                    "configuration_revision",
                    "configuration_hash",
                    "status",
                    "iterations_requested",
                    "iterations_completed",
                    "input_snapshot_hash",
                    "result_snapshot_hash",
                    "trace_hash",
                    "runtime_metadata",
                    "warnings",
                    "failure_reason",
                    "title",
                    "comments",
                    "created_by",
                    "execution_actor",
                    "created_at",
                    "updated_at",
                    "started_at",
                    "heartbeat_at",
                    "completed_at",
                    "failed_at",
                    "cancelled_at",
                    "dispatch_state",
                )
            }
        )
        result.update(
            project_id=row.project_workspace_id,
            model_id=row.model_definition_id,
            seed=row.seed,
            revision_version=self._revision(row, review),
            progress_percent=round(100 * row.iterations_completed / row.iterations_requested, 2),
            review_status=review.status if review else "NOT_SUBMITTED",
            reviewed_by=review.reviewed_by if review else None,
            accepted_by=review.accepted_by if review else None,
            acceptance_hash=review.acceptance_hash if review else None,
        )
        grants = allowed if allowed is not None else self._allowed(row.project_workspace_id)
        actions = []
        if row.status == "QUEUED" and "execute" in grants:
            actions.append("execute")
        if row.status not in TERMINAL and "cancel" in grants:
            actions.append("cancel")
        independent = self.actor_id not in {row.created_by, row.execution_actor}
        if row.status == "COMPLETED" and independent:
            if review is None and "review" in grants:
                actions.append("review")
            if review and review.status == "IN_REVIEW" and "accept" in grants:
                actions.append("accept")
        result["allowed_actions"] = actions
        for name in ("result_summary", "convergence_status", "analytical_readiness", "result_quality"):
            result[name] = deepcopy(row.runtime_metadata.get(name)) if row.status == "COMPLETED" else None
        if include_results:
            result["results"] = deepcopy(row.result_json) if row.status == "COMPLETED" else None
            result["result_summary"] = (
                deepcopy(row.result_json.get("summary", {})) if row.status == "COMPLETED" else None
            )
            result["convergence_status"] = (
                row.result_json.get("convergence", {}).get("status") if row.status == "COMPLETED" else None
            )
            result["analytical_readiness"] = (
                row.result_json.get("analytical_readiness") if row.status == "COMPLETED" else None
            )
            result["result_quality"] = row.result_json.get("result_quality") if row.status == "COMPLETED" else None
        return result

    def options(self, project_id):
        self._permission("read", project_id)
        resolved = self.requirements(project_id)
        models = self.approved_models(project_id)
        return {
            "project_id": project_id,
            "configuration": resolved["configuration"],
            "engine_policy": resolved["policy"].get("reserved_engine_settings", {}),
            "allowed_actions": self._allowed(project_id),
            "supported_analysis_types": ["COST_QRA", "SCHEDULE_QRA"],
            "integrated_execution": "ENGINE_METHOD_NOT_SUPPORTED",
            "approved_models": models["items"],
            "approved_model_total": models["total"],
            "no_new_admin_module_required": True,
        }

    def approved_models(self, project_id, *, page=1, page_size=25):
        self._permission("read", project_id)
        query = select(
            QraModelDefinition.id,
            QraModelDefinition.model_number,
            QraModelDefinition.version,
            QraModelDefinition.hash,
            QraModelDefinition.title,
            QraModelDefinition.analysis_type,
            QraModelDefinition.status,
            QraModelDefinition.completed_at,
        ).where(
            QraModelDefinition.tenant_id == self.tenant_id,
            QraModelDefinition.project_workspace_id == project_id,
            QraModelDefinition.status == "APPROVED_FOR_ANALYSIS",
        )
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.execute(
            query.order_by(QraModelDefinition.version.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        # This is an identity picker, not a promise of currentness; preflight
        # validates only the selected model to avoid N evaluations per list.
        items = [
            {
                "id": r.id,
                "model_number": r.model_number,
                "version": r.version,
                "hash": r.hash,
                "title": r.title,
                "analysis_type": r.analysis_type,
                "status": r.status,
                "completed_at": _json(r.completed_at),
                "currentness": "REQUIRES_PREFLIGHT",
            }
            for r in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def _validate_model(self, model_id, expected_hash=None):
        row = self._row("model", model_id)
        blockers = []
        if row.status != "APPROVED_FOR_ANALYSIS":
            blockers.append("QRA_MODEL_NOT_APPROVED")
        if row.analysis_type not in {"COST_QRA", "SCHEDULE_QRA"}:
            blockers.append("ENGINE_METHOD_NOT_SUPPORTED")
        if not row.hash or expected_hash is not None and row.hash != expected_hash:
            blockers.append("MODEL_HASH_CHANGED")
        if (
            row.hash
            and _hash(
                {
                    "aggregate": row.aggregate_json,
                    "snapshot": row.snapshot_json,
                    "number": row.number,
                    "version": row.version,
                }
            )
            != row.hash
        ):
            blockers.append("MODEL_SNAPSHOT_INTEGRITY_INVALID")
        resolved = self.requirements(row.project_workspace_id)
        if (
            not resolved["applicable"]
            or resolved["configuration"]["hash"] != row.configuration_hash
            or resolved["configuration"]["id"] != row.configuration_id
        ):
            blockers.append("METHODOLOGY_NOT_CURRENT")
        latest = self.evaluate(
            row.project_workspace_id, "model", row.aggregate_json, resolved=resolved, completed_at=row.completed_at
        )
        blockers.extend(latest.get("blockers", []))
        if self._material(row.snapshot_json) != self._material(latest):
            blockers.append("QRA_MODEL_STALE")
        successors = self.db.scalars(
            select(QraModelDefinition).where(
                QraModelDefinition.tenant_id == self.tenant_id,
                QraModelDefinition.project_workspace_id == row.project_workspace_id,
                QraModelDefinition.analysis_type == row.analysis_type,
                QraModelDefinition.status == "APPROVED_FOR_ANALYSIS",
                QraModelDefinition.version > row.version,
            )
        ).all()
        if any(r.snapshot_json.get("analysis_scope") == row.snapshot_json.get("analysis_scope") for r in successors):
            blockers.append("QRA_MODEL_SUPERSEDED")
        preparers = set(row.aggregate_json.get("preparers", [])) | {row.created_by, row.submitted_by}
        if row.reviewed_by in preparers or row.approved_by in preparers:
            blockers.append("QRA_MODEL_SEPARATION_OF_DUTIES_INVALID")
        return row, resolved, sorted(set(blockers)), latest

    def _manifest(self, row, resolved):
        policy = deepcopy(resolved["policy"].get("reserved_engine_settings", {}))
        sources = {}
        for kind in ("cost", "schedule"):
            source_id = getattr(row, f"{kind}_source_assessment_id")
            if source_id:
                sources[kind] = self._row(kind, source_id)
        populations = {
            f"{kind.upper()}:{item['ref']}": item
            for kind, source in sources.items()
            for item in source.snapshot_json.get("population", [])
        }
        ranges = {p["code"]: p for p in resolved["policy"]["range_policies"]}
        families = {p["code"]: p for p in resolved["policy"]["distribution_families"]}
        inputs = []
        for original in row.aggregate_json.get("inputs", []):
            item = deepcopy(original)
            source = populations.get(f"{item['source_kind']}:{item['source_item_ref']}", {})
            item["base_value"] = float(source.get("amount", source.get("original_duration", 0)))
            rules = ranges.get(item.get("range_type"), {})
            family = families.get(item.get("distribution_family"), {})
            item["allow_negative"] = bool(
                rules.get("allow_negative", False)
                and not rules.get("zero_floor", False)
                and family.get("allow_negative", False)
            )
            item["input_type"] = "ESTIMATE_UNCERTAINTY" if item["source_kind"] == "COST" else "DURATION_UNCERTAINTY"
            item["risk_refs"] = []  # No auto-conversion of Risk Register events.
            inputs.append(item)
        from app.modules.qra_engine.calculation import engine_manifest

        manifest = {
            "analysis_type": row.analysis_type,
            "inputs": sorted(inputs, key=lambda i: (i["source_kind"], i["source_item_ref"])),
            "correlations": deepcopy(row.aggregate_json.get("correlations", {"method": "NO_CORRELATION"})),
            "policy": policy,
            "model": {"id": row.id, "number": row.model_number, "version": row.version, "hash": row.hash},
            "methodology": deepcopy(resolved["configuration"]),
            "analysis_scope": deepcopy(row.snapshot_json.get("analysis_scope", {})),
            "source_refs": deepcopy(row.snapshot_json.get("source_refs", [])),
            "contexts": deepcopy(row.snapshot_json.get("contexts", {})),
            "engine_manifest": engine_manifest(),
            "raw_samples_stored": False,
            "authority_boundary": "ANALYTICAL_ONLY_NO_SOURCE_WRITEBACK",
        }
        if "cost" in sources:
            source = sources["cost"]
            basis = source.snapshot_json.get("basis", {})
            manifest["cost"] = {
                "basis": basis.get("contingency_basis"),
                "currency": basis.get("currency"),
                "deterministic_reference": sum(float(i["amount"]) for i in source.snapshot_json["population"]),
            }
            if basis.get("target_amount") is not None:
                manifest["cost"]["target_amount"] = basis["target_amount"]
        if "schedule" in sources:
            source = sources["schedule"]
            project = self._project(row.project_workspace_id)
            refs = source.aggregate_json.get("source_refs", [])
            imported = self.adapters.schedule(project, refs[0].get("id")) if len(refs) == 1 else None
            if imported is None:
                manifest["schedule"] = {}
            else:
                # Raw P6 relationship metadata contains original units, not the
                # operational adapter's historic lag_days interpretation.
                relations = []
                for r in imported["raw_relationships"]:
                    try:
                        lag = float(r.get("lag"))
                    except (ValueError, TypeError):
                        lag = r.get("lag")
                    # Explicit P6 serialization aliases, versioned in manifest.
                    # The source ingest's unknown->FS fallback is NOT reused.
                    kind = str(r.get("relationship_type") or "").upper()
                    kind = {
                        "PR_FS": "FS",
                        "PR_SS": "SS",
                        "PR_FF": "FF",
                        "PR_SF": "SF",
                        "FINISH_TO_START": "FS",
                        "START_TO_START": "SS",
                        "FINISH_TO_FINISH": "FF",
                        "START_TO_FINISH": "SF",
                        "0": "FF",
                        "1": "FS",
                        "2": "SF",
                        "3": "SS",
                    }.get(kind, kind)
                    relations.append(
                        {
                            "predecessor": r.get("predecessor"),
                            "successor": r.get("successor"),
                            "type": kind,
                            "lag": lag,
                            "lag_unit": r.get("lag_unit"),
                        }
                    )
                selected = source.snapshot_json["population"]
                unit = policy.get("schedule_unit")
                milestone_refs = policy.get(
                    "selected_milestone_refs", sorted(i["ref"] for i in selected if i.get("milestone"))
                )
                manifest["schedule"] = {
                    "activities": deepcopy(selected),
                    "relationships": relations,
                    "calendars": deepcopy(imported["calendars"]),
                    "date_anchor": imported["data_date"],
                    "unit": unit,
                    "unit_seconds": policy.get("schedule_unit_seconds"),
                    "milestone_refs": milestone_refs,
                    "relationship_serialization_version": "explicit-p6-type-aliases-v1",
                }
                if source.snapshot_json.get("basis", {}).get("target_date"):
                    manifest["schedule"]["target_date"] = source.snapshot_json["basis"]["target_date"]
        return _json(manifest)

    def preflight(self, model_id):
        row = self._row("model", model_id)
        self._permission("read", row.project_workspace_id)
        row, resolved, blockers, preview = self._validate_model(model_id)
        if not blockers:
            from app.modules.qra_engine.calculation import validate_snapshot
            from app.modules.qra_engine.policy import engine_configuration_issues

            manifest = self._manifest(row, resolved)
            if not manifest["policy"]:
                blockers.append("ENGINE_CONFIGURATION_NOT_READY")
            else:
                blockers.extend(engine_configuration_issues(manifest["policy"]))
            blockers.extend(validate_snapshot(manifest))
        return {
            "persisted": False,
            "eligible": not blockers,
            "blockers": sorted(set(blockers)),
            "warnings": preview.get("warnings", []),
            "model_id": row.id,
            "model_hash": row.hash,
            "analysis_type": row.analysis_type,
            "configuration": resolved["configuration"],
            "engine_policy": resolved["policy"].get("reserved_engine_settings", {}),
            "input_count": len(row.aggregate_json.get("inputs", [])),
            "source_refs": deepcopy(row.snapshot_json.get("source_refs", [])),
        }

    def _number_run(self, policy):
        row = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == "qra_run",
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if row is None:
            row = AdminNumberSequence(
                tenant_id=self.tenant_id, rule_code="qra_run", scope_key="tenant", next_value=1, version=1
            )
            self.db.add(row)
            self.db.flush()
        numbering = policy["run_numbering"]
        result = f"{numbering['prefix']}{numbering['separator']}{row.next_value:0{numbering['padding']}d}"
        row.next_value += 1
        row.version += 1
        return result

    def _seed_iterations(self, payload, policy):
        iteration = policy.get("iteration_policy", {})
        if (
            not iteration
            or policy.get("seed_policy")
            not in {"USER_SPECIFIED", "SYSTEM_GENERATED_AND_PERSISTED", "FIXED_FOR_REPRODUCIBILITY"}
            or not policy.get("run_numbering")
            or policy.get("result_review", {}).get("executor_cannot_accept") is not True
            or policy.get("result_review", {}).get("require_review") is not True
        ):
            self._error(409, "ENGINE_CONFIGURATION_NOT_READY")
        count = payload.iterations if payload.iterations is not None else iteration["default"]
        if (
            count < iteration["minimum"]
            or count > iteration["maximum"]
            or payload.iterations is not None
            and not iteration.get("allow_override", False)
            and count != iteration["default"]
        ):
            self._error(422, "QRA_ITERATION_POLICY_VIOLATION")
        mode = policy["seed_policy"]
        if mode == "USER_SPECIFIED":
            if payload.seed is None:
                self._error(422, "QRA_USER_SEED_REQUIRED")
            seed = payload.seed
        elif mode == "SYSTEM_GENERATED_AND_PERSISTED":
            if payload.seed is not None:
                self._error(422, "QRA_SYSTEM_SEED_OVERRIDE_DENIED")
            seed = randbits(64)
        else:
            seed = policy.get("fixed_seed")
            if seed is None:
                self._error(409, "ENGINE_CONFIGURATION_NOT_READY")
            if payload.seed is not None and payload.seed != seed:
                self._error(422, "QRA_FIXED_SEED_OVERRIDE_DENIED")
        return int(seed), int(count)

    def create_run(self, model_id, payload, key):
        def apply():
            model = self._row("model", model_id, lock=True)
            self._permission("create", model.project_workspace_id)
            model, resolved, blockers, _ = self._validate_model(model_id)
            if blockers:
                raise HTTPException(409, detail={"code": "QRA_PRE_RUN_BLOCKED", "blockers": blockers})
            manifest = self._manifest(model, resolved)
            from app.modules.qra_engine.calculation import validate_snapshot
            from app.modules.qra_engine.policy import engine_configuration_issues

            blockers = validate_snapshot(manifest) + engine_configuration_issues(manifest["policy"])
            if blockers:
                raise HTTPException(409, detail={"code": "QRA_PRE_RUN_BLOCKED", "blockers": blockers})
            seed, count = self._seed_iterations(payload, manifest["policy"])
            row = QraRun(
                tenant_id=self.tenant_id,
                project_workspace_id=model.project_workspace_id,
                run_number=self._number_run(manifest["policy"]),
                model_definition_id=model.id,
                model_number=model.model_number,
                model_version=model.version,
                model_hash=model.hash,
                analysis_type=model.analysis_type,
                engine_version=ENGINE_VERSION,
                formula_version=FORMULA_VERSION,
                configuration_id=model.configuration_id,
                configuration_revision=model.configuration_revision,
                configuration_hash=model.configuration_hash,
                seed=str(seed),
                iterations_requested=count,
                input_snapshot_hash=_hash(manifest),
                input_snapshot_json=manifest,
                title=payload.title,
                comments=payload.comments,
                created_by=self.actor_id,
                status="QUEUED",
                iterations_completed=0,
                revision_version=1,
                runtime_metadata={"worker_lease_seconds": manifest["policy"].get("worker_lease_seconds", 600)},
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "qra.run.created",
                "QraRun",
                row.id,
                {
                    "model_hash": row.model_hash,
                    "input_hash": row.input_snapshot_hash,
                    "seed": seed,
                    "iterations": count,
                },
            )
            return self._run_out(row)

        return self._engine_command("run.create", key, {"model_id": model_id, "payload": payload.model_dump()}, apply)

    def _engine_command(self, command, key, request, apply):
        try:
            return self._command(f"engine.{command}", key, request, apply)
        except HTTPException as exc:
            audit_denial(self.db, self.tenant_id, self.actor_id, _code(exc), target_id=request.get("id"))
            raise
        except StaleDataError as exc:
            self.db.rollback()
            audit_denial(self.db, self.tenant_id, self.actor_id, "QRA_CONCURRENT_CONFLICT", target_id=request.get("id"))
            raise HTTPException(409, detail={"code": "QRA_CONCURRENT_CONFLICT"}) from exc

    def runs(self, project_id, *, page=1, page_size=25):
        self._permission("read", project_id)
        query = select(QraRun).where(QraRun.tenant_id == self.tenant_id, QraRun.project_workspace_id == project_id)
        total = self.db.scalar(
            select(func.count(QraRun.id)).where(
                QraRun.tenant_id == self.tenant_id, QraRun.project_workspace_id == project_id
            )
        )
        rows = self.db.scalars(query.order_by(QraRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        reviews = {
            r.run_id: r
            for r in self.db.scalars(
                select(QraRunReview).where(
                    QraRunReview.tenant_id == self.tenant_id, QraRunReview.run_id.in_([r.id for r in rows] or [-1])
                )
            )
        }
        allowed = self._allowed(project_id)
        return {
            "items": [self._run_out(r, review=reviews.get(r.id), allowed=allowed) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def run(self, run_id, *, summary=True):
        row = self._run(run_id)
        self._permission("read", row.project_workspace_id)
        return self._run_out(row, include_results=not summary)

    def status(self, run_id):
        row = self._run(run_id)
        self._permission("read", row.project_workspace_id)
        return self._run_out(row)

    def result_section(self, run_id, section, *, page=1, page_size=100):
        row = self._run(run_id)
        self._permission("read", row.project_workspace_id)
        if row.status != "COMPLETED":
            self._error(409, "QRA_COMPLETED_RESULT_REQUIRED")
        data = row.result_json.get(
            section,
            row.result_json.get("sensitivity", [])
            if section == "drivers"
            else []
            if section in {"percentiles", "sensitivity", "milestones"}
            else {},
        )
        if section == "provenance" and isinstance(data, dict):
            data = {**data, "result_snapshot_hash": row.result_snapshot_hash, "trace_hash": row.trace_hash}
        if isinstance(data, list):
            return {
                "run_id": row.id,
                "run_hash": row.result_snapshot_hash,
                "historical": True,
                "section": section,
                "data": deepcopy(data[(page - 1) * page_size : page * page_size]),
                "total": len(data),
                "page": page,
                "page_size": page_size,
            }
        return {
            "run_id": row.id,
            "run_hash": row.result_snapshot_hash,
            "historical": True,
            "section": section,
            "data": deepcopy(data),
        }

    def execute(self, run_id, expected, payload, key):
        def apply():
            row = self._run(run_id, lock=True)
            self._permission("execute", row.project_workspace_id)
            self._version(self._revision(row), expected)
            if row.status != "QUEUED":
                self._error(409, "QRA_RUN_NOT_QUEUED")
            _, _, blockers, _ = self._validate_model(row.model_definition_id, row.model_hash)
            if blockers:
                raise HTTPException(409, detail={"code": "QRA_PRE_RUN_BLOCKED", "blockers": blockers})
            if not row.task_id:
                row.execution_actor = self.actor_id
                row.task_id = f"qra-run-{self.tenant_id}-{row.id}-{uuid4().hex}"
                row.dispatch_state = "PENDING"
                self._touch(row)
                self._event(
                    "qra.run.execution_requested",
                    "QraRun",
                    row.id,
                    {"task_id": row.task_id, "comments": payload.comments},
                )
            return self._run_out(row)

        result = self._engine_command(
            "run.execute", key, {"id": run_id, "expected": expected, "payload": payload.model_dump()}, apply
        )
        # The receipt/run commits before any broker operation. Redelivery uses
        # the same task id; a DB CAS makes duplicate deliveries harmless.
        self._dispatch(run_id)
        return result

    def _dispatch(self, run_id):
        row = self._run(run_id)
        if row.status != "QUEUED" or row.dispatch_state == "PUBLISHED" or not row.task_id:
            return
        try:
            if self.dispatcher is not None:
                self.dispatcher(self.tenant_id, row.id, row.task_id)
            else:
                from app.modules.qra_engine.tasks import execute_qra_run

                execute_qra_run.apply_async(args=[self.tenant_id, row.id], task_id=row.task_id, queue="control-core")
        except Exception as exc:
            self.db.rollback()
            row = self._run(run_id, lock=True)
            if row.status == "QUEUED":
                row.dispatch_state = "BROKER_UNAVAILABLE"
                row.runtime_metadata = {**row.runtime_metadata, "dispatch_error": type(exc).__name__}
                self._touch(row)
                self._event("qra.run.dispatch_failed", "QraRun", row.id, {"error_type": type(exc).__name__})
                self.db.commit()
            return
        self.db.rollback()
        row = self._run(run_id, lock=True)
        if row.status == "QUEUED":
            row.dispatch_state = "PUBLISHED"
            self._touch(row)
            self._event("qra.run.dispatched", "QraRun", row.id, {"task_id": row.task_id})
            self.db.commit()

    def cancel(self, run_id, expected, payload, key):
        def apply():
            row = self._run(run_id, lock=True)
            self._permission("cancel", row.project_workspace_id)
            self._version(self._revision(row), expected)
            if row.status in TERMINAL:
                self._error(409, "QRA_RUN_TERMINAL")
            row.status, row.cancelled_at = "CANCELLED", utc_now()
            row.result_json = {}
            self._touch(row)
            self._event("qra.run.cancelled", "QraRun", row.id, {"comments": payload.comments})
            return self._run_out(row)

        return self._engine_command(
            "run.cancel", key, {"id": run_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def review_action(self, run_id, expected, payload, key, action):
        def apply():
            row = self._run(run_id, lock=True)
            self._permission(action, row.project_workspace_id)
            review = self._review(run_id, lock=True)
            self._version(self._revision(row, review), expected)
            if row.status != "COMPLETED":
                self._error(409, "QRA_COMPLETED_RESULT_REQUIRED")
            if self.actor_id in {row.created_by, row.execution_actor}:
                self._error(403, "QRA_RUN_SEPARATION_OF_DUTIES")
            _, _, blockers, _ = self._validate_model(row.model_definition_id, row.model_hash)
            if blockers:
                raise HTTPException(409, detail={"code": "QRA_RESULT_NOT_CURRENT", "blockers": blockers})
            if row.result_json.get("analytical_readiness") not in {"READY", "READY_WITH_WARNINGS"}:
                self._error(409, "QRA_RESULT_ANALYTICALLY_BLOCKED")
            if action == "review":
                if review is not None:
                    self._error(409, "QRA_RESULT_ALREADY_REVIEWED")
                review = QraRunReview(
                    tenant_id=self.tenant_id,
                    run_id=row.id,
                    reviewed_by=self.actor_id,
                    review_comments=payload.comments,
                    status="IN_REVIEW",
                    revision_version=1,
                )
                self.db.add(review)
            else:
                if review is None or review.status != "IN_REVIEW":
                    self._error(409, "QRA_RESULT_REVIEW_REQUIRED")
                review.status, review.accepted_by, review.accepted_at = "ACCEPTED", self.actor_id, utc_now()
                review.acceptance_comments = payload.comments
                review.acceptance_hash = _hash(
                    {
                        "run_hash": row.result_snapshot_hash,
                        "trace_hash": row.trace_hash,
                        "reviewer": review.reviewed_by,
                        "acceptor": self.actor_id,
                        "accepted_at": review.accepted_at.isoformat(),
                        "comments": payload.comments,
                    }
                )
                review.revision_version += 1
            self.db.flush()
            self._event(
                f"qra.run.{action}",
                "QraRun",
                row.id,
                {
                    "result_hash": row.result_snapshot_hash,
                    "acceptance_hash": review.acceptance_hash,
                    "comments": payload.comments,
                    "not_fid_approval": True,
                },
            )
            return self._run_out(row, include_results=True, review=review)

        return self._engine_command(
            f"run.{action}", key, {"id": run_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def evidence(self, run_id):
        row = self._run(run_id)
        self._permission("read", row.project_workspace_id)
        review = self._review(row.id)
        blockers = []
        if row.status != "COMPLETED" or not review or review.status != "ACCEPTED":
            blockers.append("QRA_ACCEPTED_RESULT_REQUIRED")
        if row.status == "COMPLETED":
            _, _, current_blockers, _ = self._validate_model(row.model_definition_id, row.model_hash)
            blockers.extend(current_blockers)
            newer = self.db.scalars(
                select(QraRun)
                .join(QraRunReview, QraRunReview.run_id == QraRun.id)
                .where(
                    QraRun.tenant_id == self.tenant_id,
                    QraRun.project_workspace_id == row.project_workspace_id,
                    QraRun.analysis_type == row.analysis_type,
                    QraRun.id > row.id,
                    QraRunReview.status == "ACCEPTED",
                )
            ).all()
            if any(
                r.input_snapshot_json.get("analysis_scope") == row.input_snapshot_json.get("analysis_scope")
                for r in newer
            ):
                blockers.append("QRA_RESULT_SUPERSEDED")
            if row.result_snapshot_hash != _hash(row.result_json):
                blockers.append("QRA_RESULT_INTEGRITY_INVALID")
        available = not blockers
        result = row.result_json if row.status == "COMPLETED" else {}
        probabilities = {k: v for k, v in result.get("summary", {}).items() if k.startswith("probability_")}
        summary = result.get("summary", {})
        semantics = {
            key: summary[key]
            for key in (
                "currency",
                "cost_basis",
                "deterministic_reference",
                "target_amount",
                "unit",
                "date_anchor",
                "schedule_method",
                "target_date",
            )
            if key in summary
        }
        scope = deepcopy(row.input_snapshot_json.get("analysis_scope", {}))
        scope_refs = scope.get("refs", [])
        if len(scope_refs) > 200:
            scope["refs"] = scope_refs[:200]
            scope["refs_total"] = len(scope_refs)
            scope["refs_preview_only"] = True
        scope["scope_hash"] = _hash(row.input_snapshot_json.get("analysis_scope", {}))
        return {
            "provider_key": PROVIDER_KEY,
            "source_module": "QRA_CALCULATION_ENGINE",
            "evidence_type": "QRA_RESULT",
            "scope": "EACH_PROJECT",
            "project_id": row.project_workspace_id,
            "run_id": row.id,
            "run_number": row.run_number,
            "analysis_type": row.analysis_type,
            "analysis_scope": scope,
            "result_semantics": semantics,
            "model_definition_id": row.model_definition_id,
            "model_hash": row.model_hash,
            "run_hash": row.result_snapshot_hash,
            "trace_hash": row.trace_hash,
            "engine_version": row.engine_version,
            "selected_percentiles": deepcopy(result.get("percentiles", [])),
            "target_probabilities": probabilities,
            "convergence": deepcopy(result.get("convergence", {})),
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "source_current": available,
            "evidence_hash": review.acceptance_hash if available else None,
            "acceptance_hash": review.acceptance_hash if review else None,
            "quality": result.get("result_quality"),
            "readiness": result.get("analytical_readiness"),
            "warnings": deepcopy(result.get("warnings", [])),
            "blockers": sorted(set(blockers)),
            "as_of": _json(row.completed_at),
            "evidence_refs": [{"reference": f"qra-run:{row.id}", "hash": row.result_snapshot_hash}],
            "not_investment_approval": True,
            "raw_samples": "NOT_EXPOSED",
        }

    def provider_evidence(self, project_id, analysis_type=None):
        self._permission("read", project_id)
        query = (
            select(QraRun)
            .join(QraRunReview, QraRunReview.run_id == QraRun.id)
            .where(
                QraRun.tenant_id == self.tenant_id,
                QraRun.project_workspace_id == project_id,
                QraRunReview.status == "ACCEPTED",
            )
        )
        if analysis_type:
            query = query.where(QraRun.analysis_type == analysis_type)
        row = self.db.scalar(query.order_by(QraRun.id.desc()).limit(1))
        if row:
            return self.evidence(row.id)
        return {
            "provider_key": PROVIDER_KEY,
            "source_module": "QRA_CALCULATION_ENGINE",
            "evidence_type": "QRA_RESULT",
            "scope": "EACH_PROJECT",
            "project_id": project_id,
            "status": "UNAVAILABLE",
            "source_current": False,
            "evidence_hash": None,
            "blockers": ["QRA_ACCEPTED_RESULT_REQUIRED"],
            "not_investment_approval": True,
        }

    def compare(self, left_id, right_id):
        left, right = self._run(left_id), self._run(right_id)
        for row in (left, right):
            self._permission("read", row.project_workspace_id)
            if row.status != "COMPLETED":
                self._error(409, "QRA_COMPLETED_RESULT_REQUIRED")
        a, b = left.input_snapshot_json, right.input_snapshot_json
        compatible = (
            left.project_workspace_id == right.project_workspace_id
            and left.analysis_type == right.analysis_type
            and a.get("analysis_scope") == b.get("analysis_scope")
        )
        if left.analysis_type == "COST_QRA":
            compatible = (
                compatible
                and a.get("cost", {}).get("currency") == b.get("cost", {}).get("currency")
                and a.get("cost", {}).get("basis") == b.get("cost", {}).get("basis")
            )
        else:
            compatible = compatible and all(
                a.get("schedule", {}).get(k) == b.get("schedule", {}).get(k)
                for k in ("unit", "unit_seconds", "date_anchor")
            )
        if not compatible:
            self._error(422, "QRA_RUNS_INCOMPATIBLE")
        la, rb = left.result_json, right.result_json

        def indexed(values):
            return {str(v.get("percentile")): v for v in values if isinstance(v, dict)}

        lp, rp = indexed(la.get("percentiles", [])), indexed(rb.get("percentiles", []))
        deltas = [
            {
                "percentile": key,
                "left": lp[key],
                "right": rp[key],
                "delta": rp[key].get("value", 0) - lp[key].get("value", 0),
            }
            for key in sorted(lp.keys() & rp.keys())
        ]
        target_left = {k: v for k, v in la.get("summary", {}).items() if k.startswith("probability_")}
        target_right = {k: v for k, v in rb.get("summary", {}).items() if k.startswith("probability_")}
        summary_left, summary_right = la.get("summary", {}), rb.get("summary", {})
        reference_keys = {
            "probability_exceeding_deterministic_reference": "deterministic_reference",
            "probability_meeting_target_amount": "target_amount",
            "probability_meeting_target_date": "target_date",
        }
        probability_deltas = {
            key: target_right[key] - target_left[key]
            for key in target_left.keys() & target_right.keys()
            if summary_left.get(reference_keys.get(key)) == summary_right.get(reference_keys.get(key))
        }
        probability_comparison = {
            key: "COMPARABLE" if key in probability_deltas else "NOT_COMPARABLE_REFERENCE_CHANGED"
            for key in target_left.keys() & target_right.keys()
        }
        ld = {d["input_ref"]: d for d in la.get("sensitivity", [])}
        rd = {d["input_ref"]: d for d in rb.get("sensitivity", [])}
        common_drivers = sorted(ld.keys() & rd.keys())
        driver_deltas = [
            {
                "input_ref": ref,
                "left_coefficient": ld[ref]["coefficient"],
                "right_coefficient": rd[ref]["coefficient"],
                "delta": None
                if ld[ref]["coefficient"] is None or rd[ref]["coefficient"] is None
                else rd[ref]["coefficient"] - ld[ref]["coefficient"],
            }
            for ref in common_drivers[:200]
        ]
        return {
            "compatible": True,
            "left_id": left.id,
            "right_id": right.id,
            "mean_delta": rb.get("summary", {}).get("mean", 0) - la.get("summary", {}).get("mean", 0),
            "percentile_deltas": deltas,
            "model_changed": left.model_hash != right.model_hash,
            "model_hash_left": left.model_hash,
            "model_hash_right": right.model_hash,
            "source_changed": a.get("source_refs") != b.get("source_refs"),
            "source_refs_left": a.get("source_refs"),
            "source_refs_right": b.get("source_refs"),
            "engine_changed": left.engine_version != right.engine_version,
            "seed_changed": left.seed != right.seed,
            "iterations_changed": left.iterations_requested != right.iterations_requested,
            "target_probability_left": target_left,
            "target_probability_right": target_right,
            "target_probability_deltas": probability_deltas,
            "target_probability_comparability": probability_comparison,
            "target_values_left": {
                key: summary_left.get(key) for key in ("target_amount", "target_date", "deterministic_reference")
            },
            "target_values_right": {
                key: summary_right.get(key) for key in ("target_amount", "target_date", "deterministic_reference")
            },
            "target_changed": any(
                summary_left.get(key) != summary_right.get(key) for key in ("target_amount", "target_date")
            ),
            "driver_deltas": driver_deltas,
            "driver_delta_total": len(common_drivers),
            "no_fx_conversion": True,
            "no_schedule_unit_conversion": True,
        }

    def worker_execute(self, run_id, task_id, *, calculate_fn=None):
        """Idempotent DB claim; each checkpoint commits progress and releases locks."""
        from app.modules.qra_engine.calculation import (
            EngineCalculationError,
            EngineCancelled,
            calculate,
            engine_manifest,
        )

        row = self._run(run_id)
        if row.task_id != task_id or row.execution_actor is None or row.status != "QUEUED":
            return {"run_id": run_id, "status": row.status, "claimed": False}
        actor = row.execution_actor
        self.db.rollback()
        claimed = self.db.execute(
            update(QraRun)
            .where(
                QraRun.id == run_id,
                QraRun.tenant_id == self.tenant_id,
                QraRun.status == "QUEUED",
                QraRun.task_id == task_id,
            )
            .values(
                status="VALIDATING",
                started_at=utc_now(),
                heartbeat_at=utc_now(),
                updated_at=utc_now(),
                revision_version=QraRun.revision_version + 1,
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        self.db.commit()
        if claimed != 1:
            return {"run_id": run_id, "claimed": False}
        self.actor_id = actor
        begin = perf_counter()
        try:
            context = require_enterprise_permission(
                self.db, self.tenant_id, actor, PERMISSIONS["execute"], bootstrap=False
            )
            self.context = context
            self._permission("execute", self._run(run_id).project_workspace_id)
            row = self._run(run_id, lock=True)
            if row.status == "CANCELLED":
                raise EngineCancelled()
            if row.status != "VALIDATING" or row.task_id != task_id or row.execution_actor != actor:
                raise EngineCalculationError("QRA_EXECUTION_CLAIM_LOST")
            _, _, blockers, _ = self._validate_model(row.model_definition_id, row.model_hash)
            if blockers:
                raise EngineCalculationError("QRA_WORKER_REVALIDATION_BLOCKED:" + ",".join(blockers))
            manifest = deepcopy(row.input_snapshot_json)
            if _hash(manifest) != row.input_snapshot_hash:
                raise EngineCalculationError("QRA_INPUT_SNAPSHOT_INTEGRITY_INVALID")
            if manifest.get("engine_manifest") != engine_manifest():
                raise EngineCalculationError("QRA_ENGINE_ENVIRONMENT_VERSION_CHANGED")
            row.status = "RUNNING"
            self._touch(row)
            self._event("qra.run.started", "QraRun", row.id, {"task_id": task_id})
            self.db.commit()
            seed, count = int(row.seed), row.iterations_requested
            checkpoint_writes = 0

            def progress(completed, *_args, **_kwargs):
                nonlocal checkpoint_writes
                self.db.rollback()
                current = self._run(run_id, lock=True)
                if current.status == "CANCELLED":
                    raise EngineCancelled()
                if current.status != "RUNNING" or current.task_id != task_id:
                    raise EngineCalculationError("QRA_EXECUTION_CLAIM_LOST")
                current.iterations_completed = int(completed)
                current.heartbeat_at = utc_now()
                self._touch(current)
                self.db.commit()
                checkpoint_writes += 1

            results = (calculate_fn or calculate)(manifest, seed=seed, iterations=count, progress_callback=progress)
            self.db.rollback()
            row = self._run(run_id, lock=True)
            if row.status == "CANCELLED":
                raise EngineCancelled()
            if row.status != "RUNNING" or row.task_id != task_id or row.execution_actor != actor:
                raise EngineCalculationError("QRA_EXECUTION_CLAIM_LOST")
            # Last revalidation guards source changes during execution. Results
            # are never governed final evidence for a stale execution context.
            self._permission("execute", row.project_workspace_id)
            _, _, blockers, _ = self._validate_model(row.model_definition_id, row.model_hash)
            if blockers:
                raise EngineCalculationError("QRA_COMPLETION_REVALIDATION_BLOCKED:" + ",".join(blockers))
            # Decimal strings preserve all 64 seed bits across JSON/JavaScript.
            results["seed"] = row.seed
            results["provenance"] = {
                "model": manifest["model"],
                "methodology": manifest["methodology"],
                "source_refs": manifest["source_refs"],
                "input_snapshot_hash": row.input_snapshot_hash,
                "seed": row.seed,
                "iterations": count,
                "analysis_scope": manifest["analysis_scope"],
                "engine_manifest": manifest["engine_manifest"],
                "correlation": {
                    "definition_hash": _hash(manifest["correlations"]),
                    "method": manifest["correlations"].get("method"),
                    "sampling_method": manifest["policy"].get("correlation_sampling"),
                    "no_silent_psd_repair": True,
                },
                "distribution_families": sorted(
                    {i["distribution_family"] for i in manifest["inputs"] if i.get("distribution_family")}
                ),
                "input_count": len(manifest["inputs"]),
            }
            if results.get("analytical_contingency_indicator"):
                results["summary"]["analytical_contingency_indicator"] = deepcopy(
                    results["analytical_contingency_indicator"]
                )
            row.result_json = _json(results)
            row.result_snapshot_hash = _hash(row.result_json)
            row.trace_hash = _hash(
                {
                    "input_hash": row.input_snapshot_hash,
                    "result_hash": row.result_snapshot_hash,
                    "model_hash": row.model_hash,
                    "methodology_hash": row.configuration_hash,
                    "engine": row.engine_version,
                    "formula": row.formula_version,
                    "seed": seed,
                    "iterations": count,
                    "manifest": results.get("engine_manifest", {}),
                }
            )
            row.status, row.completed_at = "COMPLETED", utc_now()
            row.iterations_completed, row.heartbeat_at = count, utc_now()
            row.warnings = deepcopy(results.get("warnings", []))
            row.runtime_metadata = {
                "worker_lease_seconds": row.runtime_metadata.get("worker_lease_seconds", 600),
                "wall_seconds": round(perf_counter() - begin, 6),
                "checkpoint_writes": checkpoint_writes,
                "task_id": task_id,
                "raw_samples_stored": False,
                "worker_claim": "DATABASE_COMPARE_AND_SWAP",
                "result_summary": deepcopy(results.get("summary", {})),
                "convergence_status": results.get("convergence", {}).get("status"),
                "analytical_readiness": results.get("analytical_readiness"),
                "result_quality": results.get("result_quality"),
            }
            self._touch(row)
            self._event(
                "qra.run.completed",
                "QraRun",
                row.id,
                {
                    "result_hash": row.result_snapshot_hash,
                    "trace_hash": row.trace_hash,
                    "source_authorities_unchanged": True,
                },
            )
            self.db.commit()
            return {"run_id": row.id, "status": row.status, "result_hash": row.result_snapshot_hash, "claimed": True}
        except EngineCancelled:
            self.db.rollback()
            row = self._run(run_id, lock=True)
            if row.status not in TERMINAL:
                row.status, row.cancelled_at = "CANCELLED", utc_now()
                row.result_json = {}
                self._touch(row)
                self._event(
                    "qra.run.cancelled",
                    "QraRun",
                    row.id,
                    {"mechanism": "WORKER_CANCELLATION", "partial_results_discarded": True},
                )
                self.db.commit()
            return {"run_id": run_id, "status": row.status, "claimed": True}
        except Exception as exc:
            self.db.rollback()
            row = self._run(run_id, lock=True)
            if row.status not in TERMINAL:
                row.status, row.failed_at = "FAILED", utc_now()
                row.failure_reason = (
                    _code(exc)
                    if isinstance(exc, HTTPException)
                    else str(getattr(exc, "code", "QRA_EXECUTION_FAILED:" + type(exc).__name__))
                )[:240]
                row.result_json = {}
                row.result_snapshot_hash, row.trace_hash = None, None
                row.runtime_metadata = {
                    "worker_lease_seconds": row.runtime_metadata.get("worker_lease_seconds", 600),
                    "wall_seconds": round(perf_counter() - begin, 6),
                    "error_type": type(exc).__name__,
                    "partial_results_discarded": True,
                }
                self._touch(row)
                self._event(
                    "qra.run.failed",
                    "QraRun",
                    row.id,
                    {"reason": row.failure_reason, "source_authorities_unchanged": True},
                )
                self.db.commit()
            return {"run_id": run_id, "status": row.status, "failure_reason": row.failure_reason, "claimed": True}

    def recover_expired_workers(self, *, lease_seconds=600):
        """Worker crash is an explicit failed historical attempt, never hidden rerun."""
        # Read active attempts only. Their frozen approved lease can differ by
        # methodology; expiry is never measured against a mutable global policy.
        rows = self.db.scalars(
            select(QraRun)
            .where(QraRun.tenant_id == self.tenant_id, QraRun.status.in_(["VALIDATING", "RUNNING"]))
            .with_for_update()
        ).all()
        ids = []
        for row in rows:
            configured = row.runtime_metadata.get("worker_lease_seconds", lease_seconds)
            deadline = utc_now() - timedelta(seconds=configured)
            if row.heartbeat_at is None or row.heartbeat_at >= deadline:
                continue
            row.status, row.failed_at, row.failure_reason = "FAILED", utc_now(), "QRA_WORKER_LEASE_EXPIRED"
            row.result_json, row.result_snapshot_hash, row.trace_hash = {}, None, None
            self._touch(row)
            self._event("qra.run.worker_expired", "QraRun", row.id, {"new_run_required": True})
            ids.append(row.id)
        self.db.commit()
        return {"failed_run_ids": ids}
