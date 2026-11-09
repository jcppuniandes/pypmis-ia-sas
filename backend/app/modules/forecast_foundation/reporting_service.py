"""Read-only operational projections and explicit immutable publication commands."""

from copy import deepcopy

from sqlalchemy import select

from app.core.time import utc_now
from app.modules.basic_data.service import _hash, _json
from app.modules.forecast_foundation.models import ForecastComponent, ForecastVersion
from app.modules.forecast_foundation.policy import DEFAULT_PROFILE
from app.modules.forecast_foundation.reporting_models import ForecastLookAheadSnapshot, ForecastReportSnapshot
from app.modules.forecast_foundation.reporting_policy import (
    TREND_EVENT_LINKAGE,
    ZERO,
    business_date,
    cumulative_series,
    dashboard_indicators,
    finish_variance,
    forecast_phase_points,
    latest_report_revisions,
    lookahead_projection,
    narrative_sections,
    near_critical,
    number,
    package_activity_context,
    package_dependency_context,
    physical_progress_variance,
    readiness_rollup,
    scalar,
    snapshot_series,
    trend_series,
)
from app.modules.forecast_foundation.service import ForecastFoundationService
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.progress_foundation.integration_models import (
    EarnedValueSnapshot,
    ProgressPeriodSnapshot,
    ProjectControlBaselineBundle,
)


class ForecastReportingService(ForecastFoundationService):
    def _pinned_reporting_profile(self, identity, content_hash):
        profile = self._profile(identity)
        if profile.content_hash != content_hash or profile.status != "published":
            self._error(409, "REPORT_PINNED_FORECAST_POLICY_INVALID")
        return profile

    def _context(self, workspace, identity, *, action="read", period_id=None, as_of=None):
        project = self._project(workspace)
        self._permission(action, project)
        row = self._get(ForecastVersion, workspace, identity)
        if period_id is not None and period_id != row.period_id:
            self._error(422, "REPORT_FORECAST_PERIOD_MISMATCH")
        if as_of is not None and business_date(as_of) != row.as_of:
            self._error(422, "REPORT_FORECAST_AS_OF_MISMATCH")
        profile = self._pinned_reporting_profile(row.configuration_id, row.configuration_hash)
        if row.status in {"APPROVED", "REJECTED"}:
            result = self.calculation_result(workspace, identity)
            source = deepcopy(row.source_snapshot_json)
        else:
            self._permission("eac.view", project)
            result, source = self._calculate(row, profile)
            result = result | {"frozen": False, "preview_only": True, "forecast_status": row.status}
        return row, profile, source, result

    @staticmethod
    def _aggregate_value(result):
        values = result.get("items", []) if isinstance(result, dict) else []
        if len(values) != 1 or values[0].get("status") != "COMPUTABLE":
            return None
        return values[0].get("progress_value")

    def _cost_period(self, row, source, result):
        actuals = deepcopy(source.get("actuals", []))
        values = {
            "authority": "DERIVED_COST_PERIOD_READ_MODEL_NOT_COST_TRANSACTION",
            "period_id": row.period_id,
            "as_of": row.as_of.isoformat(),
            "currency": row.currency,
            "baseline_id": source.get("baseline_cost", {}).get("id"),
            "baseline_hash": source.get("baseline_cost", {}).get("content_hash"),
            "current_budget_id": (source.get("current_budget_version") or {}).get("id"),
            "recognized_actual_refs": [
                {
                    "id": item["id"],
                    "period_id": item["period_id"],
                    "recognition_date": item["recognition_date"],
                    "hash": _hash(item),
                }
                for item in actuals
            ],
            "actual": result.get("cost", {}).get("actual"),
            "budget": result.get("cost", {}).get("current_budget"),
            "source_hash": _hash(actuals),
        }
        return values | {"content_hash": _hash(values)}

    def _source_refs(self, row, source, result):
        return {
            "forecast": {"id": row.id, "revision": row.revision, "hash": row.content_hash, "status": row.status},
            "bundle": deepcopy(source.get("bundle", {})),
            "schedule": {
                "id": row.schedule_version_id,
                "hash": source.get("current_schedule", {}).get("content_hash"),
                "data_date": row.data_date_reference,
            },
            "progress_snapshot": {
                "authority": "APPROVED_PROGRESS_REFERENCES",
                "measurement_ids": [r["id"] for r in source.get("approved_progress", [])],
                "hash": _hash(source.get("approved_progress", [])),
            },
            "cost_period_snapshot": self._cost_period(row, source, result),
            "readiness": {
                "assessment_ids": [r["id"] for r in source.get("readiness", [])],
                "hash": _hash(source.get("readiness", [])),
                "current_readiness_hash": _hash(source.get("current_readiness", {})),
            },
            "forecast_policy": {"id": row.configuration_id, "hash": row.configuration_hash},
        }

    def performance(self, workspace, identity, *, action="read", period_id=None, as_of=None):
        row, profile, source, result = self._context(
            workspace, identity, action=action, period_id=period_id, as_of=as_of
        )
        cost, time, evm = result.get("cost", {}), result.get("time", {}), result.get("evm", {})
        progress = deepcopy(source.get("progress_projections", {}))
        progress["SCHEDULE"] = source.get("schedule_progress", progress.get("SCHEDULE", {}))
        progress["COST"] = source.get("cost_progress", progress.get("COST", {}))
        physical = self._aggregate_value(progress.get("PHYSICAL", {}))
        quantity = self._aggregate_value(progress.get("QUANTITY", {}))
        schedule_progress = progress.get("SCHEDULE", {})
        cost_progress = progress.get("COST", {})
        readiness = readiness_rollup(source.get("packages", []), source.get("current_readiness") or {})
        schedule = source.get("current_schedule", {}).get("snapshot_json", {})
        activities = schedule.get("activities", [])
        threshold = profile.content_json["lookahead"]["near_critical_threshold"]
        imported_critical = [r for r in activities if isinstance(r.get("critical"), bool)]
        compatible_float = [
            r for r in activities if r.get("total_float") is not None and r.get("float_unit") == threshold["unit"]
        ]
        constraints = [
            r for r in source.get("constraints", []) if r.get("status") not in {"CLEARED", "WAIVED", "CANCELLED"}
        ]
        errors = list(result.get("reason_codes", []))
        for domain in (cost, time, evm):
            errors.extend(domain.get("reason_codes", []))
        if physical is None:
            errors.append("APPROVED_PHYSICAL_PROGRESS_BASIS_REQUIRED")
        if quantity is None:
            errors.append("APPROVED_QUANTITY_PROGRESS_BASIS_REQUIRED")
        if readiness["status"] != "COMPUTABLE":
            errors.extend(readiness["reason_codes"])
        metrics = {
            **{name: evm.get(name) for name in ("pv", "ev", "ac", "cpi", "spi")},
            **{
                name: cost.get(name)
                for name in (
                    "bac",
                    "original_budget",
                    "current_budget",
                    "actual",
                    "commitment",
                    "committed_etc",
                    "uncommitted_etc",
                    "allowance",
                    "etc",
                    "eac",
                    "vac",
                )
            },
            **{
                name: time.get(name)
                for name in ("baseline_finish", "current_finish", "forecast_finish", "finish_variance_days")
            },
            "currency": row.currency,
            "physical_progress": physical,
            "quantity_progress": quantity,
            "schedule_progress": deepcopy(schedule_progress.get("items", [])),
            "cost_progress": deepcopy(cost_progress.get("items", [])),
            "earned_progress": scalar(number(evm["ev"]) * 100 / number(cost["bac"]))
            if evm.get("ev") is not None and cost.get("bac") is not None and number(cost["bac"]) > ZERO
            else None,
            "readiness": readiness["readiness_percent"],
            "open_constraints": len(constraints),
            "critical_count": sum(r.get("critical") is True for r in imported_critical) if imported_critical else None,
            "criticality_unknown_count": len(activities) - len(imported_critical),
            "near_critical_count": sum(
                near_critical(r, threshold["value"], threshold["unit"]) is True for r in compatible_float
            )
            if compatible_float
            else None,
            "near_critical_unknown_count": len(activities) - len(compatible_float),
        }
        if metrics["finish_variance_days"] is None:
            metrics["finish_variance_days"] = finish_variance(metrics["baseline_finish"], metrics["forecast_finish"])
        refs = self._source_refs(row, source, result)
        facts = narrative_sections(metrics, refs, profile.content_json["reporting"]["narrative_sections"])
        return {
            "status": "NOT_COMPUTABLE" if errors else "COMPUTABLE",
            "reason_codes": sorted(set(errors)),
            "forecast_version_id": row.id,
            "period_id": row.period_id,
            "as_of": row.as_of.isoformat(),
            "currency": row.currency,
            "metrics": metrics,
            "dashboard_indicators": dashboard_indicators(metrics, profile.content_json["dashboard_thresholds"]),
            "progress_variance_basis": physical_progress_variance(
                source.get("baseline_cost", {}),
                progress.get("PHYSICAL", {}),
                source.get("approved_progress", []),
                pv=evm.get("pv"),
                bac=cost.get("bac"),
                currency=row.currency,
            ),
            "domains": {
                "schedule": time | {"activities": activities, "authority": "P6_IMPORTED_NO_CPM"},
                "cost": cost,
                "progress": progress,
                "forecast": {
                    "id": row.id,
                    "status": row.status,
                    "confidence": row.confidence,
                    "confidence_rationale": row.confidence_rationale,
                    "confidence_is_statistical": False,
                },
                "awp": readiness | {"constraints": constraints},
            },
            "milestones": time.get("milestones", []),
            "top_constraints": sorted(
                constraints,
                key=lambda item: (not item.get("blocking", True), item.get("due_date") or "9999", item["id"]),
            ),
            "narratives": facts,
            "source_refs": refs,
            "source_hashes": deepcopy(source.get("hashes", row.source_hashes_json)),
            "authority": {
                "forecast": "GOVERNED_PROJECTION",
                "reporting": "READ_MODEL_ONLY",
                "cpm_calculation_performed": False,
                "source_writes_performed": False,
                "finish_variance_unit": "CALENDAR_DAY_DELTA_NOT_CPM",
            },
        }

    def variance(self, workspace, identity, **kwargs):
        result = self.performance(workspace, identity, **kwargs)
        metrics = result["metrics"]
        cost_rows = [
            {
                "metric": name.upper(),
                "baseline": metrics.get("bac") if name in {"eac", "vac"} else None,
                "current": metrics.get("current_budget"),
                "actual": metrics.get("actual"),
                "forecast": metrics.get("eac"),
                "variance": metrics.get("vac"),
                "currency": result["currency"],
                "status": result["domains"]["cost"].get("status", "NOT_COMPUTABLE"),
            }
            for name in ("eac",)
        ]
        time_row = {
            "metric": "FINISH",
            "baseline": metrics.get("baseline_finish"),
            "current": metrics.get("current_finish"),
            "actual": None,
            "forecast": metrics.get("forecast_finish"),
            "variance": metrics.get("finish_variance_days"),
            "unit": "CALENDAR_DAY_DELTA_NOT_CPM",
            "status": "COMPUTABLE" if metrics.get("finish_variance_days") is not None else "NOT_COMPUTABLE",
        }
        result["items"] = cost_rows + [time_row]
        result["progress_variances"] = {
            "approved_physical_progress": metrics.get("physical_progress"),
            "quantity_progress": metrics.get("quantity_progress"),
            "schedule_progress": metrics.get("schedule_progress"),
            "cost_progress": metrics.get("cost_progress"),
            "earned_progress": metrics.get("earned_progress"),
            **result["progress_variance_basis"],
        }
        return result

    def dashboard(self, workspace, identity, *, executive=False, **kwargs):
        result = self.performance(
            workspace, identity, action="executive.view" if executive else "dashboard.view", **kwargs
        )
        project = self._project(workspace)
        result["project_status"] = project.status
        result["view"] = "EXECUTIVE" if executive else "PROJECT_CONTROLS"
        result["risk_issue_references"] = [
            {
                "code": item["code"],
                "kind": item["kind"],
                "source_reference": item["source_reference"],
                "evidence_ref": item["evidence_ref"],
            }
            for item in self._version_out(self._get(ForecastVersion, workspace, identity))["assumptions"]
            if item["kind"].upper() in {"RISK", "ISSUE", "TREND", "POTENTIAL_CHANGE", "CLAIM"}
        ]
        return result

    def _enriched_activities(self, source, version):
        snapshot = source.get("current_schedule", {}).get("snapshot_json", {})
        scope = {r["id"]: r for r in source.get("baseline_scope", {}).get("snapshot_json", {}).get("items", [])}
        plans = {r["id"]: r for r in source.get("plans", [])}
        packages = {r["id"]: r for r in source.get("packages", [])}
        mappings = source.get("effective_package_mappings") or source.get("package_mappings", [])
        latest = {}
        for mapping in mappings:
            key = (
                mapping["work_package_id"],
                mapping.get("target_kind"),
                mapping.get("target_id"),
                mapping.get("schedule_version_id"),
                mapping.get("activity_external_id"),
                mapping.get("phase"),
            )
            latest[key] = mapping
        mappings = [
            r for r in latest.values() if r.get("status") == "ACTIVE" and r.get("mapping_health", "VALID") == "VALID"
        ]
        constraint_mappings = source.get("constraint_mappings", [])
        latest_constraints = {}
        for mapping in constraint_mappings:
            key = (
                mapping["constraint_id"],
                mapping["target_kind"],
                mapping.get("target_id"),
                mapping.get("schedule_version_id"),
                mapping.get("activity_external_id"),
            )
            latest_constraints[key] = mapping
        constraint_mappings = [r for r in latest_constraints.values() if r.get("status") == "ACTIVE"]
        cwas = {r["id"]: r for r in source.get("cwas", [])}
        readiness = source.get("current_readiness", {})
        forecasts = {
            r.activity_external_id: r
            for r in self._rows(ForecastComponent, version.project_workspace_id)
            if r.forecast_version_id == version.id and r.component_kind == "TIME" and r.activity_external_id
        }
        result = []
        for activity in snapshot.get("activities", []):
            row = deepcopy(activity)
            identity = str(row["external_id"])
            linked = [
                r
                for r in source.get("current_schedule_mappings", [])
                if r.get("status") == "VALID"
                and (
                    r.get("target_kind") == "ACTIVITY"
                    and str(r.get("target_external_id")) == identity
                    or r.get("target_kind") == "WBS"
                    and str(r.get("target_external_id")) == str(row.get("wbs_external_id"))
                )
            ]
            plan_ids = {i for r in linked for i in r.get("plan_item_ids", [])}
            scope_ids = {i for r in linked for i in r.get("resolved_scope_item_ids", r.get("scope_item_ids", []))}
            for allocation in source.get("plan_allocations", []):
                if allocation.get("plan_item_id") in plan_ids:
                    scope_ids.add(allocation["scope_item_id"])
            package_context = package_activity_context(
                mappings,
                plan_ids=plan_ids,
                scope_ids=scope_ids,
                schedule_version_id=version.schedule_version_id,
                activity_external_id=identity,
            )
            package_ids = set(package_context["work_package_ids"])
            dependencies = package_dependency_context(source.get("package_dependencies", []), packages, package_ids)
            direct_ids = {
                proof["work_package_id"] for proof in package_context["proofs"] if proof["via"] == "DIRECT_ACTIVITY"
            }
            for r in mappings:
                if r["work_package_id"] in direct_ids:
                    if r["target_kind"] == "PLAN":
                        plan_ids.add(r["target_id"])
                    if r["target_kind"] == "SCOPE":
                        scope_ids.add(r["target_id"])
                    scope_ids.update(r.get("lineage_json", {}).get("resolved_scope_item_ids", []))
            for allocation in source.get("plan_allocations", []):
                if allocation.get("plan_item_id") in plan_ids:
                    scope_ids.add(allocation["scope_item_id"])
            cwa_ids = {packages[i].get("cwa_id") for i in package_ids if i in packages and packages[i].get("cwa_id")}
            cwa_ancestors = set(cwa_ids)
            for cwa in list(cwa_ids):
                while (
                    cwa and cwas.get(cwa, {}).get("parent_cwa_id") and cwas[cwa]["parent_cwa_id"] not in cwa_ancestors
                ):
                    cwa = cwas[cwa]["parent_cwa_id"]
                    cwa_ancestors.add(cwa)
            constraint_ids = set()
            for mapping in constraint_mappings:
                if (
                    mapping["target_kind"] == "PACKAGE"
                    and mapping.get("target_id") in package_ids
                    or mapping["target_kind"] == "PLAN"
                    and mapping.get("target_id") in plan_ids
                    or mapping["target_kind"] == "SCOPE"
                    and mapping.get("target_id") in scope_ids
                    or mapping["target_kind"] == "CWA"
                    and mapping.get("target_id") in cwa_ancestors
                    or mapping["target_kind"] == "ACTIVITY"
                    and mapping.get("schedule_version_id") == version.schedule_version_id
                    and str(mapping.get("activity_external_id")) == identity
                ):
                    constraint_ids.add(mapping["constraint_id"])
            constraints = [
                deepcopy(r)
                for r in source.get("constraints", [])
                if r["id"] in constraint_ids and r.get("status") not in {"CLEARED", "WAIVED", "CANCELLED"}
            ]
            row.update(
                {
                    "scope_item_ids": sorted(scope_ids),
                    "plan_item_ids": sorted(plan_ids),
                    "work_package_ids": sorted(package_ids),
                    "package_join_context": package_context,
                    "cwa_ids": sorted(cwa_ids),
                    "constraints": constraints,
                    "blocking_constraint_ids": sorted(r["id"] for r in constraints if r.get("blocking")),
                    "package_dependencies": dependencies,
                    "blocking_dependency_ids": dependencies["blocking_ids"],
                    "readiness": [readiness[str(i)] for i in sorted(package_ids) if str(i) in readiness],
                    "plan_items": [plans[i] for i in sorted(plan_ids) if i in plans],
                    "packages": [packages[i] for i in sorted(package_ids) if i in packages],
                    "scope_items": [scope[i] for i in sorted(scope_ids) if i in scope],
                    "source_schedule_version": version.schedule_version_id,
                }
            )
            for dimension in ("area", "zone", "system", "discipline"):
                row[dimension + "s"] = sorted(
                    {str(scope[i][dimension]) for i in scope_ids if i in scope and scope[i].get(dimension)}
                )
            if identity in forecasts:
                row["forecast_finish"] = (
                    forecasts[identity].forecast_finish.isoformat() if forecasts[identity].forecast_finish else None
                )
            result.append(row)
        return result

    def lookahead(self, workspace, payload, *, period_id=None, as_of=None):
        row, profile, source, _ = self._context(
            workspace, payload.forecast_version_id, action="lookahead.view", period_id=period_id, as_of=as_of
        )
        policy = profile.content_json["lookahead"]
        horizon = payload.horizon_days or policy["default_horizon_days"]
        if horizon > policy["maximum_horizon_days"]:
            self._error(422, "LOOKAHEAD_HORIZON_DISABLED_BY_POLICY")
        threshold = policy["near_critical_threshold"]
        snapshot = source.get("current_schedule", {}).get("snapshot_json", {})
        result = lookahead_projection(
            self._enriched_activities(source, row),
            snapshot.get("wbs", []),
            snapshot.get("relationships", []),
            as_of=row.as_of,
            horizon_days=horizon,
            include_overdue=policy["include_overdue"],
            exclude_milestones=payload.exclude_milestones
            if payload.exclude_milestones is not None
            else policy["exclude_milestones"],
            group_by=payload.group_by or policy["group_by"],
            top_n=payload.top_n if payload.top_n is not None else policy["default_top_n"],
            critical_only=payload.critical_only,
            near_critical_value=payload.near_critical_value
            if payload.near_critical_value is not None
            else threshold["value"],
            near_critical_unit=payload.near_critical_unit or threshold["unit"],
            wbs_external_id=payload.wbs_external_id,
            work_package_id=payload.work_package_id,
        )
        result.update(
            {
                "forecast_version_id": row.id,
                "period_id": row.period_id,
                "source_refs": {
                    "schedule_version_id": row.schedule_version_id,
                    "schedule_hash": source.get("current_schedule", {}).get("content_hash"),
                    "forecast_version_id": row.id,
                    "forecast_hash": row.content_hash,
                },
                "source_hashes": deepcopy(source.get("hashes", row.source_hashes_json)),
            }
        )
        return result

    def generate_lookahead(self, workspace, payload, key):
        self._permission("lookahead.generate", self._project(workspace))

        def apply():
            row = self._get(ForecastVersion, workspace, payload.forecast_version_id)
            if row.status != "APPROVED":
                self._error(409, "LOOKAHEAD_APPROVED_FORECAST_REQUIRED")
            result = self.lookahead(workspace, payload)
            record = ForecastLookAheadSnapshot(
                **self._base(workspace),
                forecast_version_id=row.id,
                period_id=row.period_id,
                as_of=row.as_of,
                schedule_version_id=row.schedule_version_id,
                configuration_id=row.configuration_id,
                configuration_hash=row.configuration_hash,
                query_json=payload.model_dump(mode="json"),
                result_snapshot_json=_json(result),
                source_refs_json=result["source_refs"],
                content_hash=_hash(result),
                reason=payload.reason,
            )
            self.db.add(record)
            return self._record(record, "LOOKAHEAD_GENERATED", payload.reason)

        return self._write("lookahead.generate", workspace, payload, key, apply)

    def _latest_reports(self, workspace):
        periods = {r.id: r for r in self._rows(ProjectControlsPeriod, workspace)}
        families = {}
        for identity in periods:
            current, visited = identity, set()
            while current in periods and periods[current].reopen_parent_id and current not in visited:
                visited.add(current)
                current = periods[current].reopen_parent_id
            families[identity] = current
        records = [
            self._out(r) | {"period_revision": periods[r.period_id].revision}
            for r in self._rows(ForecastReportSnapshot, workspace)
        ]
        return latest_report_revisions(records, families)

    def trends(self, workspace, *, forecast_version_id=None):
        project = self._project(workspace)
        self._permission("read", project)
        reports = self._latest_reports(workspace)
        if forecast_version_id is not None:
            forecast = self._get(ForecastVersion, workspace, forecast_version_id)
            profile = self._pinned_reporting_profile(forecast.configuration_id, forecast.configuration_hash)
        elif reports:
            latest = reports[-1]
            profile = self._pinned_reporting_profile(latest["configuration_id"], latest["configuration_hash"])
        else:
            profile = self._forecast_profile(project)
        rows = [
            {
                "id": r["id"],
                "period_id": r["period_id"],
                "as_of": r["as_of"],
                "revision": r["revision"],
                "forecast_version_id": r["forecast_version_id"],
                "metrics": deepcopy(r["metrics_json"]["metrics"]),
                "currency": r["metrics_json"].get("currency"),
                "source_refs": deepcopy(r["source_refs_json"]),
                "content_hash": r["content_hash"],
            }
            for r in reports
        ]
        metrics = (profile.content_json if profile else DEFAULT_PROFILE)["trend_metrics"]
        return {
            "status": "COMPUTABLE" if reports else "NOT_COMPUTABLE",
            "reason_codes": [] if reports else ["PUBLISHED_PERIOD_REPORT_REQUIRED"],
            "items": rows,
            "series": trend_series(rows, metrics),
            "forecast_policy": {"id": profile.id, "hash": profile.content_hash} if profile else None,
            "authority": "IMMUTABLE_PUBLISHED_REPORTS_LATEST_REVISION_PER_PERIOD_FAMILY",
            "history_preserved": True,
        }

    def curves(self, workspace, identity, *, period_id=None, as_of=None):
        row, profile, source, result = self._context(workspace, identity, period_id=period_id, as_of=as_of)
        refs = self._source_refs(row, source, result)
        baseline = source.get("baseline_cost", {})
        phase_points = [
            {
                "date": p["date"],
                "value": p["amount"],
                "unit": "MONEY",
                "currency": phase.get("currency"),
                "source_refs": [{"cost_baseline_id": baseline.get("id"), "phase_id": phase.get("id")}],
            }
            for phase in baseline.get("snapshot_json", {}).get("phasing", [])
            for p in phase.get("spread_json", [])
        ]
        pv = cumulative_series(
            phase_points,
            code="PLANNED_VALUE",
            unit="MONEY",
            currency=row.currency,
            basis="APPROVED_COST_BASELINE_PHASING",
            source_refs=refs,
        )
        bac = result.get("cost", {}).get("bac")
        planned = {
            **deepcopy(pv),
            "code": "PLANNED_PROGRESS",
            "unit": "%",
            "currency": None,
            "basis": "APPROVED_BUDGET_WEIGHTED_PLANNED_VALUE_OVER_BAC_NOT_PHYSICAL_MEASUREMENT",
        }
        if pv["status"] == "COMPUTABLE" and bac is not None and number(bac) > ZERO:
            planned["points"] = [
                {
                    **point,
                    "period_value": scalar(number(point["period_value"]) * 100 / number(bac)),
                    "cumulative_value": scalar(number(point["cumulative_value"]) * 100 / number(bac)),
                }
                for point in pv["points"]
            ]
        else:
            planned.update(
                status="NOT_COMPUTABLE", reason_codes=["POSITIVE_APPROVED_BAC_AND_PHASING_REQUIRED"], points=[]
            )
        reports = [
            r
            for r in self._latest_reports(workspace)
            if r["bundle_id"] == row.bundle_id and r["as_of"] <= row.as_of.isoformat()
        ]
        snapshots = {
            r["as_of"]: {
                "date": r["as_of"],
                "physical": r["metrics_json"]["metrics"].get("physical_progress"),
                "earned": r["metrics_json"]["metrics"].get("ev"),
                "source_refs": [{"report_id": r["id"], "hash": r["content_hash"]}],
            }
            for r in reports
        }
        physical = self._aggregate_value(source.get("progress_projections", {}).get("PHYSICAL", {}))
        snapshots[row.as_of.isoformat()] = {
            "date": row.as_of.isoformat(),
            "physical": physical,
            "earned": result.get("evm", {}).get("ev"),
            "source_refs": [{"forecast_version_id": row.id, "hash": row.content_hash}],
        }
        physical_curve = snapshot_series(
            [{"date": r["date"], "value": r["physical"], "source_refs": r["source_refs"]} for r in snapshots.values()],
            code="APPROVED_ACTUAL_PROGRESS",
            unit="%",
            basis="APPROVED_PHYSICAL_PROGRESS_SNAPSHOT_NOT_PERIOD_SUM",
            source_refs=refs,
        )
        earned_curve = snapshot_series(
            [{"date": r["date"], "value": r["earned"], "source_refs": r["source_refs"]} for r in snapshots.values()],
            code="EARNED_VALUE",
            unit="MONEY",
            currency=row.currency,
            basis="O1BD_APPROVED_EARNED_VALUE_SNAPSHOT",
            source_refs=refs,
        )
        actual_by_id = {r["id"]: r for r in source.get("actuals", [])}
        actual_points = [
            {
                "date": r["recognition_date"],
                "value": r["amount"],
                "currency": r["currency"],
                "unit": "MONEY",
                "source_refs": [{"actual_id": r["id"], "period_id": r["period_id"], "hash": _hash(r)}],
            }
            for r in actual_by_id.values()
        ]
        actual_curve = cumulative_series(
            actual_points,
            code="ACTUAL_COST",
            unit="MONEY",
            currency=row.currency,
            basis="RECOGNIZED_COST_ON_RECOGNITION_DATE_UNIQUE_SOURCE_IDS",
            source_refs=refs,
        )
        components = [
            r
            for r in self._rows(ForecastComponent, workspace)
            if r.forecast_version_id == row.id and r.component_kind == "COST"
        ]
        calculated_cost_items = {item["id"]: item for item in result.get("cost", {}).get("items", [])}
        future, future_errors = forecast_phase_points(
            [
                {
                    "id": component.id,
                    "content_hash": component.content_hash,
                    "amount": calculated_cost_items.get(component.id, {}).get("amount", component.amount),
                    "currency": component.currency,
                    "phasing": calculated_cost_items.get(component.id, {}).get(
                        "phasing", component.inputs.get("forecast_spread", component.inputs.get("phasing", []))
                    ),
                }
                for component in components
            ],
            as_of=row.as_of,
            currency=row.currency,
        )
        forecast_curve = cumulative_series(
            actual_points + future,
            code="FORECAST_COST",
            unit="MONEY",
            currency=row.currency,
            basis="RECOGNIZED_ACTUAL_PLUS_EXPLICIT_APPROVED_FORECAST_ETC_PHASING",
            source_refs=refs,
        )
        if result.get("cost", {}).get("status") != "COMPUTABLE":
            future_errors.append("COMPUTABLE_FORECAST_COST_REQUIRED")
        if (
            forecast_curve["points"]
            and result.get("cost", {}).get("eac") is not None
            and number(forecast_curve["points"][-1]["cumulative_value"]) != number(result["cost"]["eac"])
        ):
            future_errors.append("FORECAST_COST_CURVE_EAC_RECONCILIATION_REQUIRED")
        if future_errors:
            forecast_curve.update(status="NOT_COMPUTABLE", reason_codes=sorted(set(future_errors)), points=[])
        available = {
            series["code"]: series
            for series in (planned, physical_curve, earned_curve, pv, actual_curve, forecast_curve)
        }
        series = [available[code] for code in profile.content_json["s_curve_series"]]
        return {
            "status": "COMPUTABLE" if all(r["status"] == "COMPUTABLE" for r in series) else "NOT_COMPUTABLE",
            "reason_codes": sorted({reason for r in series for reason in r["reason_codes"]}),
            "series": series,
            "forecast_version_id": row.id,
            "period_id": row.period_id,
            "as_of": row.as_of.isoformat(),
            "source_refs": refs,
            "authority": "COMPATIBLE_GOVERNED_SERIES_NO_UNIT_OR_CURRENCY_MIX",
        }

    def reports(self, workspace):
        self._permission("report.read", self._project(workspace))
        rows = self._rows(ForecastReportSnapshot, workspace)
        return {"items": [self._out(row) for row in rows], "total": len(rows), "history_immutable": True}

    def report(self, workspace, identity):
        self._permission("report.read", self._project(workspace))
        return self._out(self._get(ForecastReportSnapshot, workspace, identity))

    def publish_report(self, workspace, payload, key, *, predecessor=None, expected=None):
        self._permission("report.republish" if predecessor else "report.publish", self._project(workspace))

        def apply():
            forecast = self._get(ForecastVersion, workspace, payload.forecast_version_id, lock=True)
            if forecast.status != "APPROVED":
                self._error(409, "REPORT_APPROVED_FORECAST_REQUIRED")
            period = self._get(ProjectControlsPeriod, workspace, forecast.period_id, lock=True)
            if period.status != "PUBLISHED":
                self._error(409, "REPORT_PUBLISHED_PERIOD_REQUIRED")
            profile = self._profile(forecast.configuration_id)
            policy = profile.content_json["reporting"]
            if (
                policy["publisher_not_forecast_preparer"]
                and self.actor_id in {forecast.prepared_by, forecast.updated_by}
                or policy["publisher_not_forecast_approver"]
                and self.actor_id == forecast.approved_by
            ):
                self._error(403, "REPORT_PUBLICATION_SOD")
            old = self._get(ForecastReportSnapshot, workspace, predecessor, lock=True) if predecessor else None
            existing = [r for r in self._rows(ForecastReportSnapshot, workspace) if r.period_id == period.id]
            if old:
                self._version(old.version, expected)
                if not policy["allow_republish"] or old.period_id != period.id:
                    self._error(409, "REPORT_REPUBLISH_PERIOD_OR_POLICY_MISMATCH")
                if old.id != max(existing, key=lambda r: r.revision).id:
                    self._error(409, "REPORT_LATEST_SUCCESSOR_REQUIRED")
                if forecast.supersedes_id != old.forecast_version_id:
                    self._error(409, "REPORT_FORECAST_SUCCESSOR_REQUIRED")
            elif existing:
                self._error(409, "REPORT_EXPLICIT_REPUBLISH_SUCCESSOR_REQUIRED")
            progress = self.db.scalar(
                select(ProgressPeriodSnapshot).where(
                    ProgressPeriodSnapshot.tenant_id == self.tenant_id,
                    ProgressPeriodSnapshot.project_workspace_id == workspace,
                    ProgressPeriodSnapshot.period_id == period.id,
                    ProgressPeriodSnapshot.status == "PUBLISHED",
                )
            )
            if progress is None or _hash(progress.report_snapshot_json) != progress.content_hash:
                self._error(409, "REPORT_PUBLISHED_PROGRESS_SNAPSHOT_REQUIRED")
            evms = [
                r
                for r in self._rows(EarnedValueSnapshot, workspace)
                if r.bundle_id == forecast.bundle_id and r.period_id == period.id and r.as_of == forecast.as_of
            ]
            frozen_evm = forecast.result_json.get("evm", {})
            evms = [
                r
                for r in evms
                if r.content_hash == _hash(r.snapshot_json) and _json(r.snapshot_json) == _json(frozen_evm)
            ]
            if not evms:
                self._error(409, "REPORT_MATCHING_FROZEN_EVM_SNAPSHOT_REQUIRED")
            evm = evms[-1]
            source = forecast.source_snapshot_json
            assessments = source.get("readiness", [])
            package_ids = {r["id"] for r in source.get("packages", [])}
            if policy["require_readiness_assessments"] and not package_ids <= {
                r["work_package_id"] for r in assessments
            }:
                self._error(409, "REPORT_READINESS_ASSESSMENT_REQUIRED")
            if any(
                business_date(r.get("as_of")) is not None and business_date(r["as_of"]) > forecast.as_of
                for r in assessments
            ):
                self._error(409, "REPORT_READINESS_AS_OF_MISMATCH")
            bundle = self._get(ProjectControlBaselineBundle, workspace, forecast.bundle_id)
            projection = self.performance(workspace, forecast.id)
            refs = projection["source_refs"]
            refs["progress_snapshot"] = {
                "id": progress.id,
                "hash": progress.content_hash,
                "status": progress.status,
                "measurement_ids": [r["id"] for r in progress.report_snapshot_json.get("approved_measurements", [])],
            }
            refs["evm_snapshot"] = {"id": evm.id, "hash": evm.content_hash, "status": evm.status}
            projection["source_refs"] = refs
            narratives = narrative_sections(projection["metrics"], refs, policy["narrative_sections"])
            allowed_refs = {"forecast", "cost", "awp", "schedule", "progress", "evm"}
            for item in payload.narratives:
                if item.section not in policy["narrative_sections"] or not set(item.fact_references) <= allowed_refs:
                    self._error(422, "REPORT_NARRATIVE_SOURCE_FACT_REFERENCE_INVALID")
                narratives = [r for r in narratives if r["section"] != item.section]
                narratives.append(item.model_dump(mode="json") | {"authored_by": self.actor_id})
            frozen_source = {
                "forecast": {"id": forecast.id, "hash": forecast.content_hash},
                "period": self._out(period),
                "cost_period_snapshot": self._cost_period(forecast, source, forecast.result_json),
                "readiness_snapshot": deepcopy(source.get("current_readiness", {})),
                "readiness_assessment_refs": [{"id": r["id"], "hash": _hash(r)} for r in assessments],
            }
            content = {
                "source_refs": refs,
                "source_snapshot": frozen_source,
                "metrics": projection,
                "narratives": narratives,
            }
            row = ForecastReportSnapshot(
                **self._base(workspace),
                forecast_version_id=forecast.id,
                bundle_id=bundle.id,
                period_id=period.id,
                as_of=forecast.as_of,
                schedule_version_id=forecast.schedule_version_id,
                cost_baseline_id=bundle.cost_baseline_id,
                progress_snapshot_id=progress.id,
                evm_snapshot_id=evm.id,
                configuration_id=forecast.configuration_id,
                configuration_hash=forecast.configuration_hash,
                revision=max((r.revision for r in existing), default=0) + 1,
                supersedes_id=old.id if old else None,
                status="PUBLISHED",
                source_refs_json=_json(refs),
                source_snapshot_json=_json(frozen_source),
                metrics_json=_json(projection),
                narratives_json=_json(narratives),
                content_hash=_hash(content),
                published_by=self.actor_id,
                published_at=utc_now(),
                reason=payload.reason,
                evidence_reference=payload.evidence_reference,
            )
            self.db.add(row)
            self.db.flush()
            self._event("REPORT_SNAPSHOT_CREATED", row.id, {"period_id": period.id, "forecast_version_id": forecast.id})
            return self._record(row, "REPORT_REPUBLISHED" if old else "REPORT_PUBLISHED", payload.reason)

        return self._write(
            "report.republish" if predecessor else "report.publish",
            workspace,
            payload,
            key,
            apply,
            predecessor,
            expected,
        )

    def analytics_contract(self, workspace):
        self._permission("report.read", self._project(workspace))
        return {
            "schema_version": 1,
            "authority": "GOVERNED_READ_MODEL_NOT_TRANSACTIONAL_POWER_BI",
            "refresh_semantics": "READ_LATEST_PUBLISHED_REPORT_REVISION_EXPLICIT_REFRESH",
            "history_semantics": "REPORT_ID_AND_CONTENT_HASH_PIN_IMMUTABLE_RESULT",
            "write_back_supported": False,
            "trend_event_linkage": deepcopy(TREND_EVENT_LINKAGE),
            "reports": [
                {
                    "id": r["id"],
                    "period_id": r["period_id"],
                    "revision": r["revision"],
                    "as_of": r["as_of"],
                    "content_hash": r["content_hash"],
                }
                for r in self._latest_reports(workspace)
            ],
        }
