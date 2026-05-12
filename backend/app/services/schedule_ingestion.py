from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    WBS,
    Activity,
    ActivityRelationship,
    BaselineVersion,
    Budget,
    BusinessProcessInstance,
    BusinessProcessStepTemplate,
    BusinessProcessTemplate,
    ControlAccount,
    ControlAccountMapping,
    ControlPeriod,
    ImportStatus,
    RelationshipType,
    ScheduleActivityMap,
    ScheduleImport,
    ScheduleSource,
    ScheduleValidationFinding,
    WorkflowStepInstance,
)


@dataclass(frozen=True)
class ParsedActivity:
    external_id: str
    name: str
    wbs_code: str = ""
    wbs_name: str = ""
    planned_start: date | None = None
    planned_finish: date | None = None
    total_float_days: float = 0
    critical_path: bool = False
    planned_cost: float = 0


@dataclass(frozen=True)
class ParsedRelationship:
    predecessor: str
    successor: str
    relationship_type: RelationshipType = RelationshipType.fs
    lag_days: float = 0


@dataclass(frozen=True)
class ValidationFinding:
    check_code: str
    severity: str
    message: str
    item_count: int
    weight: float


@dataclass(frozen=True)
class ParsedSchedule:
    source: ScheduleSource
    activities: list[ParsedActivity]
    relationships: list[ParsedRelationship]
    data_date: date | None
    baseline_name: str
    validation_summary: str
    quality_score: float
    findings: list[ValidationFinding]


class ScheduleIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def ingest(self, tenant_id: int, project_id: int, file_name: str, content: bytes) -> ScheduleImport:
        parsed = self.parse(file_name, content)
        rejected = not parsed.activities or any(finding.severity == "error" for finding in parsed.findings)
        status = ImportStatus.rejected if rejected else ImportStatus.validated

        schedule_import = ScheduleImport(
            tenant_id=tenant_id,
            project_id=project_id,
            source=parsed.source,
            file_name=file_name,
            status=status,
            data_date=parsed.data_date,
            baseline_name=parsed.baseline_name,
            quality_score=parsed.quality_score,
            validation_summary=parsed.validation_summary,
        )
        self.db.add(schedule_import)
        self.db.flush()

        schedule_rows: list[tuple[ScheduleActivityMap, ParsedActivity]] = []
        for parsed_activity in parsed.activities:
            schedule_row = ScheduleActivityMap(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                activity_id=None,
                external_activity_id=parsed_activity.external_id,
                wbs_code=parsed_activity.wbs_code,
                activity_name=parsed_activity.name,
                planned_start=parsed_activity.planned_start,
                planned_finish=parsed_activity.planned_finish,
                total_float_days=parsed_activity.total_float_days,
                critical_path=parsed_activity.critical_path,
            )
            self.db.add(schedule_row)
            schedule_rows.append((schedule_row, parsed_activity))

        for relationship in parsed.relationships:
            self.db.add(
                ActivityRelationship(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    schedule_import_id=schedule_import.id,
                    predecessor_external_id=relationship.predecessor,
                    successor_external_id=relationship.successor,
                    relationship_type=relationship.relationship_type,
                    lag_days=relationship.lag_days,
                )
            )

        for finding in parsed.findings:
            self.db.add(
                ScheduleValidationFinding(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    schedule_import_id=schedule_import.id,
                    check_code=finding.check_code,
                    severity=finding.severity,
                    message=finding.message,
                    item_count=finding.item_count,
                    weight=finding.weight,
                )
            )

        self.db.flush()
        if status == ImportStatus.validated:
            self._materialize_control_structure(tenant_id, project_id, schedule_import, schedule_rows)

        self._create_baseline_version(tenant_id, project_id, schedule_import)
        self._ensure_control_period(tenant_id, project_id, parsed.data_date)
        self.start_schedule_workflow(tenant_id, project_id, schedule_import)
        self.db.commit()
        self.db.refresh(schedule_import)
        return schedule_import

    def start_schedule_workflow(
        self,
        tenant_id: int,
        project_id: int,
        schedule_import: ScheduleImport,
    ) -> BusinessProcessInstance:
        accepted = schedule_import.status == ImportStatus.validated
        process = BusinessProcessInstance(
            tenant_id=tenant_id,
            project_id=project_id,
            trigger_entity_type="ScheduleImport",
            trigger_entity_id=schedule_import.id,
            process_code="SCH-INTAKE",
            process_name="Schedule Intake",
            record_no=f"SCH-{schedule_import.id:05d}",
            title=f"Schedule Intake - {schedule_import.file_name}",
            status="in_review" if accepted else "rejected",
            current_step="Impact Review" if accepted else "Data Quality Gate",
            ball_in_court="Project Controls" if accepted else "Planning Lead",
        )
        self.db.add(process)
        self.db.flush()

        step_rows = (
            [
                ("Creation", "Source schedule file received.", "Planner", "Complete", "complete"),
                (
                    "Data Quality",
                    "DCMA/AACE schedule quality, logic and baseline checks passed.",
                    "Controls Engineer",
                    "Complete",
                    "complete",
                ),
                (
                    "Impact Review",
                    "Schedule, cost, progress and contractual exposure analysis.",
                    "Project Controls",
                    "Active",
                    "active",
                ),
                (
                    "Approval",
                    "Control Manager decision on baseline acceptance.",
                    "Control Manager",
                    "Pending",
                    "pending",
                ),
                (
                    "Action",
                    "Forecast, lookahead, communication and audit updates.",
                    "Execution Lead",
                    "Queued",
                    "queued",
                ),
            ]
            if accepted
            else [
                ("Creation", "Source schedule file received.", "Planner", "Complete", "complete"),
                (
                    "Data Quality",
                    "Import failed the required schedule quality gate.",
                    "Controls Engineer",
                    "Rejected",
                    "critical",
                ),
                (
                    "Impact Review",
                    "Blocked until the schedule file is corrected and reloaded.",
                    "Project Controls",
                    "Blocked",
                    "queued",
                ),
                (
                    "Approval",
                    "No approval route until the data quality gate passes.",
                    "Control Manager",
                    "Queued",
                    "queued",
                ),
                (
                    "Action",
                    "Execution feedback remains pending a valid schedule baseline.",
                    "Execution Lead",
                    "Queued",
                    "queued",
                ),
            ]
        )
        configured_step_rows = self._template_step_rows(tenant_id, "SCH-INTAKE")
        if configured_step_rows:
            step_rows = self._schedule_state_rows(configured_step_rows, accepted)

        for order, (name, detail, owner_role, status, tone) in enumerate(step_rows, start=1):
            self.db.add(
                WorkflowStepInstance(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    process_instance_id=process.id,
                    step_order=order,
                    name=name,
                    detail=detail,
                    owner_role=owner_role,
                    status=status,
                    tone=tone,
                )
            )

        return process

    def _template_step_rows(self, tenant_id: int, process_code: str) -> list[tuple[str, str, str, str, str]]:
        template = self.db.scalar(
            select(BusinessProcessTemplate).where(
                BusinessProcessTemplate.tenant_id == tenant_id,
                BusinessProcessTemplate.code == process_code,
            )
        )
        if not template:
            return []
        steps = list(
            self.db.scalars(
                select(BusinessProcessStepTemplate)
                .where(
                    BusinessProcessStepTemplate.tenant_id == tenant_id,
                    BusinessProcessStepTemplate.template_id == template.id,
                )
                .order_by(BusinessProcessStepTemplate.step_order)
            ).all()
        )
        return [(step.name, step.detail, step.owner_role, step.status, step.tone) for step in steps]

    def _schedule_state_rows(
        self,
        step_rows: list[tuple[str, str, str, str, str]],
        accepted: bool,
    ) -> list[tuple[str, str, str, str, str]]:
        if accepted:
            return step_rows
        rejected: list[tuple[str, str, str, str, str]] = []
        for name, detail, owner_role, _status, _tone in step_rows:
            if name == "Creation":
                rejected.append((name, "Source schedule file received.", owner_role, "Complete", "complete"))
            elif name == "Data Quality":
                rejected.append(
                    (name, "Import failed the required schedule quality gate.", owner_role, "Rejected", "critical")
                )
            elif name == "Impact Review":
                rejected.append(
                    (
                        name,
                        "Blocked until the schedule file is corrected and reloaded.",
                        owner_role,
                        "Blocked",
                        "queued",
                    )
                )
            else:
                rejected.append((name, detail, owner_role, "Queued", "queued"))
        return rejected

    def parse(self, file_name: str, content: bytes) -> ParsedSchedule:
        source = self.detect_source(file_name, content)
        data_date: date | None = None
        if source == ScheduleSource.p6_xer:
            activities, relationships, data_date = self._parse_xer(content)
        elif source in {ScheduleSource.p6_xml, ScheduleSource.ms_project_xml}:
            activities, relationships, data_date = self._parse_xml(content, source)
        else:
            activities, relationships = [], []

        findings, quality_score, validation_summary = self._validate_schedule(activities, relationships)
        return ParsedSchedule(
            source=source,
            activities=activities,
            relationships=relationships,
            data_date=data_date,
            baseline_name=Path(file_name).stem,
            validation_summary=validation_summary,
            quality_score=quality_score,
            findings=findings,
        )

    def detect_source(self, file_name: str, content: bytes) -> ScheduleSource:
        suffix = Path(file_name).suffix.lower()
        sample = content[:4000].decode("utf-8", errors="ignore").lower()
        if suffix == ".xer":
            return ScheduleSource.p6_xer
        if suffix == ".mpp":
            return ScheduleSource.ms_project_mpp
        if "primavera" in sample or "apibo" in sample or "<activity" in sample:
            return ScheduleSource.p6_xml
        return ScheduleSource.ms_project_xml

    def _parse_xer(self, content: bytes) -> tuple[list[ParsedActivity], list[ParsedRelationship], date | None]:
        rows_by_table = self._xer_rows(content)
        wbs_rows = rows_by_table.get("PROJWBS", []) or rows_by_table.get("WBS", [])
        wbs_by_id = {
            row.get("wbs_id", ""): {
                "code": row.get("wbs_short_name") or row.get("wbs_code") or row.get("wbs_id") or "",
                "name": row.get("wbs_name") or row.get("wbs_short_name") or row.get("wbs_id") or "",
            }
            for row in wbs_rows
        }
        task_rows = rows_by_table.get("TASK", [])
        task_id_to_code = {
            row.get("task_id", ""): row.get("task_code") or row.get("task_id", "")
            for row in task_rows
            if row.get("task_id")
        }
        resource_cost_by_task = self._xer_resource_cost_by_task(rows_by_table)

        activities: list[ParsedActivity] = []
        for index, row in enumerate(task_rows, start=1):
            external_id = row.get("task_code") or row.get("task_id") or f"TASK-{index}"
            wbs = wbs_by_id.get(row.get("wbs_id", ""), {})
            total_float = self._hours_to_days(row.get("total_float_hr_cnt"))
            task_cost = self._planned_cost_from_row(row) or resource_cost_by_task.get(row.get("task_id", ""), 0)
            activities.append(
                ParsedActivity(
                    external_id=external_id,
                    name=row.get("task_name") or external_id,
                    wbs_code=wbs.get("code") or row.get("wbs_id") or "UNMAPPED",
                    wbs_name=wbs.get("name") or wbs.get("code") or "Unmapped WBS",
                    planned_start=self._parse_date(
                        row.get("target_start_date")
                        or row.get("early_start_date")
                        or row.get("act_start_date")
                        or row.get("restart_date")
                    ),
                    planned_finish=self._parse_date(
                        row.get("target_end_date")
                        or row.get("early_end_date")
                        or row.get("act_end_date")
                        or row.get("reend_date")
                    ),
                    total_float_days=total_float,
                    critical_path=(row.get("critical_flag") or "").upper() == "Y" or total_float <= 0,
                    planned_cost=task_cost,
                )
            )

        relationships = []
        for row in rows_by_table.get("TASKPRED", []):
            predecessor = task_id_to_code.get(row.get("pred_task_id", ""), row.get("pred_task_id", ""))
            successor = task_id_to_code.get(row.get("task_id", ""), row.get("task_id", ""))
            relationships.append(
                ParsedRelationship(
                    predecessor=predecessor,
                    successor=successor,
                    relationship_type=self._relationship(row.get("pred_type")),
                    lag_days=self._hours_to_days(row.get("lag_hr_cnt")),
                )
            )

        data_date = None
        project_rows = rows_by_table.get("PROJECT", [])
        if project_rows:
            data_date = self._parse_date(
                project_rows[0].get("last_recalc_date") or project_rows[0].get("plan_start_date")
            )
        return activities, [rel for rel in relationships if rel.predecessor and rel.successor], data_date

    def _parse_xml(
        self,
        content: bytes,
        source: ScheduleSource,
    ) -> tuple[list[ParsedActivity], list[ParsedRelationship], date | None]:
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError:
            return [], [], None
        if source == ScheduleSource.p6_xml:
            return self._parse_p6_xml(root)
        return self._parse_project_xml(root)

    def _parse_project_xml(
        self, root: ElementTree.Element
    ) -> tuple[list[ParsedActivity], list[ParsedRelationship], date | None]:
        activities: list[ParsedActivity] = []
        relationships: list[ParsedRelationship] = []
        tasks = [element for element in root.iter() if self._local_name(element.tag) == "Task"]

        for index, task in enumerate(tasks, start=1):
            uid = self._child_text(task, "UID") or self._child_text(task, "Id") or f"TASK-{index}"
            name = self._child_text(task, "Name") or uid
            if not name.strip():
                continue
            activities.append(
                ParsedActivity(
                    external_id=uid,
                    name=name,
                    wbs_code=self._child_text(task, "WBS") or self._child_text(task, "OutlineNumber") or "UNMAPPED",
                    wbs_name=self._child_text(task, "OutlineNumber") or self._child_text(task, "WBS") or "Unmapped WBS",
                    planned_start=self._parse_date(self._child_text(task, "Start")),
                    planned_finish=self._parse_date(self._child_text(task, "Finish")),
                    total_float_days=self._duration_to_days(self._child_text(task, "TotalSlack")),
                    critical_path=(self._child_text(task, "Critical") or "0") in {"1", "true", "True"},
                    planned_cost=self._money_to_float(
                        self._child_text(task, "Cost") or self._child_text(task, "BaselineCost")
                    ),
                )
            )
            for predecessor in [child for child in task if self._local_name(child.tag) == "PredecessorLink"]:
                relationships.append(
                    ParsedRelationship(
                        predecessor=self._child_text(predecessor, "PredecessorUID") or "",
                        successor=uid,
                        relationship_type=self._relationship(self._child_text(predecessor, "Type")),
                        lag_days=self._duration_to_days(self._child_text(predecessor, "LinkLag")),
                    )
                )

        data_date = self._parse_date(self._first_deep_text(root, ["StatusDate", "CurrentDate", "StartDate"]))
        return activities, [rel for rel in relationships if rel.predecessor and rel.successor], data_date

    def _parse_p6_xml(
        self, root: ElementTree.Element
    ) -> tuple[list[ParsedActivity], list[ParsedRelationship], date | None]:
        activity_elements = [element for element in root.iter() if self._local_name(element.tag) == "Activity"]
        activity_by_object_id: dict[str, str] = {}
        activity_refs: list[tuple[ElementTree.Element, int, str, str]] = []
        wbs_by_object_id = {
            self._child_text(element, "ObjectId"): {
                "code": self._child_text(element, "Code")
                or self._child_text(element, "Id")
                or self._child_text(element, "ObjectId"),
                "name": self._child_text(element, "Name") or self._child_text(element, "Code") or "WBS",
            }
            for element in root.iter()
            if self._local_name(element.tag) in {"WBS", "WBSNode"} and self._child_text(element, "ObjectId")
        }

        for index, activity in enumerate(activity_elements, start=1):
            object_id = self._child_text(activity, "ObjectId")
            external_id = (
                self._child_text(activity, "Id")
                or self._child_text(activity, "ActivityId")
                or self._child_text(activity, "Code")
                or object_id
                or f"ACT-{index}"
            )
            if object_id:
                activity_by_object_id[object_id] = external_id
            activity_by_object_id[external_id] = external_id
            activity_refs.append((activity, index, object_id, external_id))

        assignment_cost_by_activity = self._p6_xml_assignment_cost_by_activity(root, activity_by_object_id)

        activities: list[ParsedActivity] = []
        for activity, _index, _object_id, external_id in activity_refs:
            wbs_object_id = self._child_text(activity, "WBSObjectId")
            wbs = wbs_by_object_id.get(wbs_object_id, {})
            total_float = self._duration_to_days(
                self._child_text(activity, "TotalFloat") or self._child_text(activity, "TotalFloatDuration")
            )
            activity_cost = self._planned_xml_cost(activity) or assignment_cost_by_activity.get(external_id, 0)
            activities.append(
                ParsedActivity(
                    external_id=external_id,
                    name=self._child_text(activity, "Name") or external_id,
                    wbs_code=self._child_text(activity, "WBSCode") or wbs.get("code") or wbs_object_id or "UNMAPPED",
                    wbs_name=wbs.get("name") or self._child_text(activity, "WBSName") or "Unmapped WBS",
                    planned_start=self._parse_date(
                        self._child_text(activity, "PlannedStartDate")
                        or self._child_text(activity, "StartDate")
                        or self._child_text(activity, "RemainingEarlyStartDate")
                    ),
                    planned_finish=self._parse_date(
                        self._child_text(activity, "PlannedFinishDate")
                        or self._child_text(activity, "FinishDate")
                        or self._child_text(activity, "RemainingEarlyFinishDate")
                    ),
                    total_float_days=total_float,
                    critical_path=(self._child_text(activity, "IsCritical") or "").lower() in {"true", "1"}
                    or total_float <= 0,
                    planned_cost=activity_cost,
                )
            )

        relationships: list[ParsedRelationship] = []
        for relationship in [element for element in root.iter() if self._local_name(element.tag) == "Relationship"]:
            predecessor = activity_by_object_id.get(
                self._child_text(relationship, "PredecessorActivityObjectId"),
                self._child_text(relationship, "PredecessorActivityId"),
            )
            successor = activity_by_object_id.get(
                self._child_text(relationship, "SuccessorActivityObjectId"),
                self._child_text(relationship, "SuccessorActivityId"),
            )
            relationships.append(
                ParsedRelationship(
                    predecessor=predecessor,
                    successor=successor,
                    relationship_type=self._relationship(self._child_text(relationship, "Type")),
                    lag_days=self._duration_to_days(self._child_text(relationship, "Lag")),
                )
            )

        data_date = self._parse_date(self._first_deep_text(root, ["DataDate", "CurrentDataDate", "MustFinishByDate"]))
        return activities, [rel for rel in relationships if rel.predecessor and rel.successor], data_date

    def _validate_schedule(
        self,
        activities: list[ParsedActivity],
        relationships: list[ParsedRelationship],
    ) -> tuple[list[ValidationFinding], float, str]:
        findings: list[ValidationFinding] = []
        if not activities:
            findings.append(
                ValidationFinding("NO_ACTIVITIES", "error", "No schedule activities were parsed from the file.", 1, 100)
            )
            return findings, 0, "0 activities parsed. Schedule rejected."

        activity_ids = [activity.external_id for activity in activities]
        duplicate_ids = len(activity_ids) - len(set(activity_ids))
        missing_dates = sum(1 for activity in activities if not activity.planned_start or not activity.planned_finish)
        invalid_dates = sum(
            1
            for activity in activities
            if activity.planned_start and activity.planned_finish and activity.planned_finish < activity.planned_start
        )
        missing_wbs = sum(1 for activity in activities if not activity.wbs_code or activity.wbs_code == "UNMAPPED")
        predecessor_ids = {relationship.predecessor for relationship in relationships}
        successor_ids = {relationship.successor for relationship in relationships}
        open_starts = max(sum(1 for activity in activities if activity.external_id not in successor_ids) - 1, 0)
        open_finishes = max(sum(1 for activity in activities if activity.external_id not in predecessor_ids) - 1, 0)
        relationship_deficit = max(len(activities) - 1 - len(relationships), 0)
        leads = sum(1 for relationship in relationships if relationship.lag_days < 0)
        high_lags = sum(1 for relationship in relationships if relationship.lag_days > 10)
        high_float = sum(1 for activity in activities if activity.total_float_days > 44)
        negative_float = sum(1 for activity in activities if activity.total_float_days < 0)
        cost_loaded = sum(1 for activity in activities if activity.planned_cost > 0)

        self._add_finding(findings, duplicate_ids, "DUPLICATE_IDS", "error", "Duplicate activity IDs detected.", 10)
        self._add_finding(
            findings, missing_dates, "MISSING_DATES", "error", "Activities without start or finish dates.", 8
        )
        self._add_finding(
            findings,
            invalid_dates,
            "INVALID_DATES",
            "error",
            "Activities with finish date earlier than start date.",
            10,
        )
        self._add_finding(
            findings,
            relationship_deficit,
            "LOGIC_DENSITY",
            "warning",
            "Logic density below minimum activity chain expectation.",
            5,
        )
        self._add_finding(
            findings, open_starts, "OPEN_STARTS", "warning", "Activities with missing predecessor logic.", 3
        )
        self._add_finding(
            findings, open_finishes, "OPEN_FINISHES", "warning", "Activities with missing successor logic.", 3
        )
        self._add_finding(findings, leads, "LEADS", "warning", "Relationships with negative lag/leads.", 5)
        self._add_finding(
            findings, high_lags, "HIGH_LAGS", "warning", "Relationships with lag greater than 10 days.", 2
        )
        self._add_finding(
            findings, high_float, "HIGH_FLOAT", "info", "Activities with total float greater than 44 days.", 1
        )
        self._add_finding(findings, negative_float, "NEGATIVE_FLOAT", "warning", "Activities with negative float.", 3)
        self._add_finding(findings, missing_wbs, "MISSING_WBS", "warning", "Activities without WBS mapping.", 3)
        if cost_loaded == 0:
            findings.append(
                ValidationFinding(
                    "NO_COST_LOADING",
                    "info",
                    "No cost-loaded activity values were found; control accounts will need budget loading.",
                    len(activities),
                    0,
                )
            )

        penalty = sum(
            finding.item_count * finding.weight for finding in findings if finding.severity in {"error", "warning"}
        )
        quality_score = max(100 - penalty, 0)
        validation_summary = (
            f"{len(activities)} activities, {len(relationships)} relationships, "
            f"{missing_dates} missing dates, {open_starts + open_finishes} open logic checks, "
            f"{leads} leads, {high_lags} high lags, {cost_loaded} cost-loaded activities."
        )
        return findings, quality_score, validation_summary

    def _materialize_control_structure(
        self,
        tenant_id: int,
        project_id: int,
        schedule_import: ScheduleImport,
        schedule_rows: list[tuple[ScheduleActivityMap, ParsedActivity]],
    ) -> None:
        wbs_cache: dict[str, WBS] = {}
        account_cache: dict[str, ControlAccount] = {}
        planned_cost_by_account: dict[int, float] = {}
        planned_value_by_account: dict[int, float] = {}
        cbs_by_account: dict[int, str] = {}

        for schedule_row, parsed_activity in schedule_rows:
            wbs_code = self._clean_code(parsed_activity.wbs_code or "UNMAPPED")
            wbs = wbs_cache.get(wbs_code) or self._get_or_create_wbs(
                tenant_id,
                project_id,
                wbs_code,
                parsed_activity.wbs_name or f"WBS {wbs_code}",
            )
            wbs_cache[wbs_code] = wbs

            account_code = f"CA-{wbs_code}"[:80]
            cbs_code = self._cbs_code(wbs_code, parsed_activity)
            account = account_cache.get(account_code) or self._get_or_create_control_account(
                tenant_id,
                project_id,
                wbs.id,
                account_code,
                f"Control Account {wbs_code}",
            )
            account_cache[account_code] = account
            planned_percent = self._planned_percent(parsed_activity, schedule_import.data_date)
            activity = self._get_or_create_activity(
                tenant_id,
                project_id,
                account.id,
                parsed_activity,
                planned_percent,
            )
            schedule_row.activity_id = activity.id
            planned_cost_by_account[account.id] = (
                planned_cost_by_account.get(account.id, 0) + parsed_activity.planned_cost
            )
            planned_value = parsed_activity.planned_cost * planned_percent / 100
            planned_value_by_account[account.id] = planned_value_by_account.get(account.id, 0) + planned_value
            cbs_by_account[account.id] = cbs_code
            self._upsert_control_account_mapping(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import=schedule_import,
                schedule_row=schedule_row,
                activity=activity,
                account=account,
                wbs=wbs,
                cbs_code=cbs_code,
                planned_cost=parsed_activity.planned_cost,
                planned_value=planned_value,
                planned_percent=planned_percent,
                status="mapped" if parsed_activity.planned_cost > 0 else "needs_cost_loading",
                review_note=""
                if parsed_activity.planned_cost > 0
                else "Activity mapped to control account, but schedule has no cost-loaded value.",
            )

        for account_id, planned_cost in planned_cost_by_account.items():
            if planned_cost <= 0:
                continue
            existing_budget = self.db.scalars(
                select(Budget).where(
                    Budget.tenant_id == tenant_id,
                    Budget.project_id == project_id,
                    Budget.control_account_id == account_id,
                )
            ).first()
            if existing_budget:
                existing_budget.cbs_code = cbs_by_account.get(account_id, existing_budget.cbs_code)
                existing_budget.bac = planned_cost
                existing_budget.cost_loaded_pv = planned_value_by_account.get(account_id, 0)
            else:
                self.db.add(
                    Budget(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        control_account_id=account_id,
                        cbs_code=cbs_by_account.get(account_id, f"CBS-{account_id}"),
                        bac=planned_cost,
                        cost_loaded_pv=planned_value_by_account.get(account_id, 0),
                    )
                )

    def _upsert_control_account_mapping(
        self,
        tenant_id: int,
        project_id: int,
        schedule_import: ScheduleImport,
        schedule_row: ScheduleActivityMap,
        activity: Activity,
        account: ControlAccount,
        wbs: WBS,
        cbs_code: str,
        planned_cost: float,
        planned_value: float,
        planned_percent: float,
        status: str,
        review_note: str,
    ) -> None:
        mapping = self.db.scalar(
            select(ControlAccountMapping).where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_activity_map_id == schedule_row.id,
            )
        )
        if not mapping:
            mapping = ControlAccountMapping(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                schedule_activity_map_id=schedule_row.id,
            )
            self.db.add(mapping)
        mapping.activity_id = activity.id
        mapping.control_account_id = account.id
        mapping.wbs_code = wbs.code
        mapping.wbs_name = wbs.name
        mapping.cbs_code = cbs_code
        mapping.mapping_rule = "WBS -> Control Account -> CBS"
        mapping.planned_cost = planned_cost
        mapping.planned_value = planned_value
        mapping.planned_percent = planned_percent
        mapping.status = status
        mapping.review_note = review_note

    def _cbs_code(self, wbs_code: str, parsed_activity: ParsedActivity) -> str:
        clean_wbs = self._clean_code(wbs_code or parsed_activity.wbs_code or "UNMAPPED")
        activity_prefix = self._clean_code(
            parsed_activity.external_id.split("-")[0] if parsed_activity.external_id else clean_wbs
        )
        return f"CBS-{clean_wbs}-{activity_prefix}"[:120]

    def _create_baseline_version(self, tenant_id: int, project_id: int, schedule_import: ScheduleImport) -> None:
        existing = self.db.scalar(
            select(BaselineVersion).where(
                BaselineVersion.tenant_id == tenant_id,
                BaselineVersion.project_id == project_id,
                BaselineVersion.schedule_import_id == schedule_import.id,
            )
        )
        if existing:
            return
        version_no = (
            self.db.scalar(
                select(func.coalesce(func.max(BaselineVersion.version_no), 0)).where(
                    BaselineVersion.tenant_id == tenant_id,
                    BaselineVersion.project_id == project_id,
                )
            )
            or 0
        ) + 1
        self.db.add(
            BaselineVersion(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                version_no=version_no,
                name=schedule_import.baseline_name,
                status="in_review" if schedule_import.status == ImportStatus.validated else "rejected",
                data_date=schedule_import.data_date,
                quality_score=schedule_import.quality_score,
            )
        )
        self.db.flush()

    def _ensure_control_period(self, tenant_id: int, project_id: int, data_date: date | None) -> None:
        if not data_date:
            return
        period_label = data_date.strftime("%Y-%m")
        existing = self.db.scalar(
            select(ControlPeriod).where(
                ControlPeriod.tenant_id == tenant_id,
                ControlPeriod.project_id == project_id,
                ControlPeriod.period_label == period_label,
            )
        )
        if existing:
            existing.data_date = data_date
            return
        self.db.add(
            ControlPeriod(
                tenant_id=tenant_id,
                project_id=project_id,
                period_label=period_label,
                data_date=data_date,
                status="open",
            )
        )

    def _get_or_create_wbs(self, tenant_id: int, project_id: int, code: str, name: str) -> WBS:
        wbs = self.db.scalar(
            select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id, WBS.code == code)
        )
        if wbs:
            wbs.name = name or wbs.name
            return wbs
        wbs = WBS(tenant_id=tenant_id, project_id=project_id, parent_id=None, code=code, name=name or f"WBS {code}")
        self.db.add(wbs)
        self.db.flush()
        return wbs

    def _get_or_create_control_account(
        self, tenant_id: int, project_id: int, wbs_id: int, code: str, name: str
    ) -> ControlAccount:
        account = self.db.scalar(
            select(ControlAccount).where(
                ControlAccount.tenant_id == tenant_id,
                ControlAccount.project_id == project_id,
                ControlAccount.code == code,
            )
        )
        if account:
            account.wbs_id = wbs_id
            return account
        account = ControlAccount(
            tenant_id=tenant_id,
            project_id=project_id,
            wbs_id=wbs_id,
            code=code,
            name=name,
            responsible="Project Controls",
            discipline="Imported Schedule",
        )
        self.db.add(account)
        self.db.flush()
        return account

    def _get_or_create_activity(
        self,
        tenant_id: int,
        project_id: int,
        control_account_id: int,
        parsed_activity: ParsedActivity,
        planned_percent: float,
    ) -> Activity:
        activity = self.db.scalar(
            select(Activity).where(
                Activity.tenant_id == tenant_id,
                Activity.project_id == project_id,
                Activity.code == parsed_activity.external_id,
            )
        )
        if not activity:
            activity = Activity(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=control_account_id,
                code=parsed_activity.external_id,
                name=parsed_activity.name,
                logic_type="FS",
                baseline_start=parsed_activity.planned_start,
                baseline_finish=parsed_activity.planned_finish,
                planned_percent=planned_percent,
                critical_path=parsed_activity.critical_path,
                lookahead_window="6W",
            )
            self.db.add(activity)
            self.db.flush()
            return activity

        activity.control_account_id = control_account_id
        activity.name = parsed_activity.name
        activity.baseline_start = parsed_activity.planned_start
        activity.baseline_finish = parsed_activity.planned_finish
        activity.planned_percent = planned_percent
        activity.critical_path = parsed_activity.critical_path
        return activity

    def _xer_rows(self, content: bytes) -> dict[str, list[dict[str, str]]]:
        text = content.decode("utf-8", errors="ignore")
        rows_by_table: dict[str, list[dict[str, str]]] = {}
        current_table = ""
        fields: list[str] = []
        for raw_line in text.splitlines():
            parts = raw_line.split("\t")
            if not parts:
                continue
            marker = parts[0]
            if marker == "%T":
                current_table = (parts[1] if len(parts) > 1 else "").upper()
                fields = []
                rows_by_table.setdefault(current_table, [])
            elif marker == "%F":
                fields = [field.strip().lower() for field in parts[1:]]
            elif marker == "%R" and current_table:
                rows_by_table.setdefault(current_table, []).append(dict(zip(fields, parts[1:], strict=False)))
        return rows_by_table

    def _xer_resource_cost_by_task(self, rows_by_table: dict[str, list[dict[str, str]]]) -> dict[str, float]:
        costs: dict[str, float] = {}
        for table_name in ("TASKRSRC", "RSRCASSIGN", "RESOURCEASSIGNMENT"):
            for row in rows_by_table.get(table_name, []):
                task_id = row.get("task_id") or row.get("activity_id") or row.get("task_code")
                if not task_id:
                    continue
                cost = self._planned_cost_from_row(row)
                if cost <= 0:
                    continue
                costs[task_id] = costs.get(task_id, 0) + cost
        return costs

    def _p6_xml_assignment_cost_by_activity(
        self,
        root: ElementTree.Element,
        activity_by_object_id: dict[str, str],
    ) -> dict[str, float]:
        costs: dict[str, float] = {}
        assignment_tags = {"ResourceAssignment", "ActivityResourceAssignment", "ActivityExpense", "ExpenseAssignment"}
        activity_ref_tags = ["ActivityObjectId", "ActivityId", "TaskObjectId", "TaskId"]
        for element in root.iter():
            if self._local_name(element.tag) not in assignment_tags:
                continue
            activity_ref = self._first_child_text(element, activity_ref_tags)
            activity_id = activity_by_object_id.get(activity_ref, activity_ref)
            if not activity_id:
                continue
            cost = self._planned_xml_cost(element)
            if cost <= 0:
                continue
            costs[activity_id] = costs.get(activity_id, 0) + cost
        return costs

    def _planned_percent(self, activity: ParsedActivity, data_date: date | None) -> float:
        if not data_date or not activity.planned_start or not activity.planned_finish:
            return 0
        if data_date <= activity.planned_start:
            return 0
        if data_date >= activity.planned_finish:
            return 100
        duration = max((activity.planned_finish - activity.planned_start).days, 1)
        elapsed = max((data_date - activity.planned_start).days, 0)
        return round(min(elapsed / duration * 100, 100), 2)

    def _add_finding(
        self,
        findings: list[ValidationFinding],
        count: int,
        check_code: str,
        severity: str,
        message: str,
        weight: float,
    ) -> None:
        if count:
            findings.append(ValidationFinding(check_code, severity, message, count, weight))

    def _clean_code(self, value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value.strip())
        return (cleaned or "UNMAPPED")[:60]

    def _relationship(self, value: str | None) -> RelationshipType:
        mapping = {
            "PR_FS": RelationshipType.fs,
            "PR_SS": RelationshipType.ss,
            "PR_FF": RelationshipType.ff,
            "PR_SF": RelationshipType.sf,
            "FINISH_TO_START": RelationshipType.fs,
            "START_TO_START": RelationshipType.ss,
            "FINISH_TO_FINISH": RelationshipType.ff,
            "START_TO_FINISH": RelationshipType.sf,
            "0": RelationshipType.ff,
            "1": RelationshipType.fs,
            "2": RelationshipType.sf,
            "3": RelationshipType.ss,
            "FS": RelationshipType.fs,
            "SS": RelationshipType.ss,
            "FF": RelationshipType.ff,
            "SF": RelationshipType.sf,
        }
        return mapping.get((value or "FS").upper(), RelationshipType.fs)

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        cleaned = value.split("T", 1)[0].split(" ", 1)[0]
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None

    def _hours_to_days(self, value: str | None) -> float:
        try:
            return round(float(value or 0) / 8, 2)
        except ValueError:
            return 0

    def _duration_to_days(self, value: str | None) -> float:
        if not value:
            return 0
        cleaned = value.strip()
        if cleaned.startswith("P") and "D" in cleaned:
            try:
                return float(cleaned.split("D", 1)[0].replace("P", "").replace("T", ""))
            except ValueError:
                return 0
        try:
            numeric = float(cleaned)
            return round(numeric / 480, 2) if numeric > 100 else numeric
        except ValueError:
            return 0

    def _money_to_float(self, value: str | None) -> float:
        if not value:
            return 0
        cleaned = value.strip()
        if not cleaned:
            return 0
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        cleaned = (
            cleaned.replace("(", "")
            .replace(")", "")
            .replace("$", "")
            .replace("USD", "")
            .replace("COP", "")
            .replace(" ", "")
        )
        if "," in cleaned and "." in cleaned and cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            parsed = float(cleaned)
            return -parsed if negative else parsed
        except ValueError:
            return 0

    def _first_float(self, row: dict[str, str], keys: list[str]) -> float:
        for key in keys:
            value = self._money_to_float(row.get(key))
            if value:
                return value
        return 0

    def _planned_cost_from_row(self, row: dict[str, str]) -> float:
        aggregate = self._first_float(
            row,
            [
                "target_cost",
                "planned_cost",
                "planned_total_cost",
                "budgeted_cost",
                "budgeted_total_cost",
                "baseline_cost",
                "at_complete_cost",
                "at_complete_total_cost",
                "total_cost",
                "remain_cost",
                "remaining_cost",
                "actual_cost",
                "act_reg_cost",
                "act_ot_cost",
                "rem_late_start_cost",
            ],
        )
        if aggregate:
            return aggregate

        component_total = sum(
            self._money_to_float(row.get(key))
            for key in [
                "target_labor_cost",
                "target_equip_cost",
                "target_material_cost",
                "target_mat_cost",
                "target_expense_cost",
                "planned_labor_cost",
                "planned_equip_cost",
                "planned_material_cost",
                "budgeted_labor_cost",
                "budgeted_equip_cost",
                "budgeted_material_cost",
            ]
        )
        if component_total:
            return component_total

        quantity = self._first_float(row, ["target_qty", "planned_qty", "budgeted_units", "remaining_qty"])
        unit_cost = self._first_float(row, ["cost_per_qty", "unit_cost", "price_per_unit"])
        return quantity * unit_cost if quantity and unit_cost else 0

    def _planned_xml_cost(self, element: ElementTree.Element) -> float:
        aggregate = self._first_child_float(
            element,
            [
                "AtCompletionTotalCost",
                "AtCompletionCost",
                "PlannedTotalCost",
                "PlannedCost",
                "BudgetedTotalCost",
                "BudgetedCost",
                "BaselineCost",
                "RemainingTotalCost",
                "RemainingCost",
                "ActualTotalCost",
                "ActualCost",
                "Cost",
            ],
        )
        if aggregate:
            return aggregate
        return sum(
            self._money_to_float(self._child_text(element, tag_name))
            for tag_name in [
                "PlannedLaborCost",
                "PlannedEquipmentCost",
                "PlannedMaterialCost",
                "BudgetedLaborCost",
                "BudgetedEquipmentCost",
                "BudgetedMaterialCost",
            ]
        )

    def _local_name(self, tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def _child_text(self, element: ElementTree.Element, tag_name: str) -> str:
        for child in element:
            if self._local_name(child.tag) == tag_name and child.text:
                return child.text.strip()
        return ""

    def _first_child_text(self, element: ElementTree.Element, tag_names: list[str]) -> str:
        for tag_name in tag_names:
            value = self._child_text(element, tag_name)
            if value:
                return value
        return ""

    def _first_child_float(self, element: ElementTree.Element, tag_names: list[str]) -> float:
        for tag_name in tag_names:
            value = self._money_to_float(self._child_text(element, tag_name))
            if value:
                return value
        return 0

    def _first_deep_text(self, root: ElementTree.Element, tag_names: list[str]) -> str:
        wanted = set(tag_names)
        for element in root.iter():
            if self._local_name(element.tag) in wanted and element.text:
                return element.text.strip()
        return ""
