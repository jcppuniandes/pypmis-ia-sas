"""Primavera P6 schedule parser (XER + XML) with DCMA validation.

Extracted from the historical ScheduleIngestionService so it can be reused
by tests, workers, and future ingestion pipelines without depending on the
SQLAlchemy session lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree


class ScheduleParseError(Exception):
    """Raised when an XER/XML payload cannot be parsed."""


@dataclass
class DCMAValidationResult:
    total_activities: int = 0
    missing_logic_count: int = 0
    missing_logic_pct: float = 0.0
    hard_constraint_count: int = 0
    high_float_count: int = 0
    negative_float_count: int = 0
    passed: bool = False

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_activities": self.total_activities,
            "missing_logic_count": self.missing_logic_count,
            "missing_logic_pct": round(self.missing_logic_pct, 2),
            "hard_constraint_count": self.hard_constraint_count,
            "high_float_count": self.high_float_count,
            "negative_float_count": self.negative_float_count,
            "passed": self.passed,
        }


@dataclass
class ParsedSchedule:
    source_type: str
    activities: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    wbs: list[dict[str, Any]] = field(default_factory=list)
    project_meta: dict[str, Any] = field(default_factory=dict)

    def dcma_validate(self) -> DCMAValidationResult:
        result = DCMAValidationResult(total_activities=len(self.activities))
        if not self.activities:
            result.passed = True
            return result

        activity_ids_with_logic: set[str] = set()
        for rel in self.relationships:
            activity_ids_with_logic.add(str(rel.get("pred_task_id", "")))
            activity_ids_with_logic.add(str(rel.get("task_id", "")))

        all_ids = {str(a.get("task_id", "")) for a in self.activities}
        missing_ids = all_ids - activity_ids_with_logic
        result.missing_logic_count = len(missing_ids)
        result.missing_logic_pct = (result.missing_logic_count / result.total_activities) * 100

        result.passed = (
            result.missing_logic_pct <= 5.0 and result.hard_constraint_count == 0 and result.negative_float_count == 0
        )
        return result


def parse_xer(content: str) -> ParsedSchedule:
    """Parse a Primavera P6 XER export.

    XER is tab-separated with section markers:
      %FMT:<version>   — file header
      %ER  <table>     — start of a table; next line is header, then data rows
      %TR  <table>     — end of a table (or trailer)
      %E               — end of file
    """

    tables: dict[str, list[dict[str, str]]] = {}
    current_table: str | None = None
    headers: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%ER"):
            current_table = line[3:].strip().split()[0] if line[3:].strip() else None
            headers = []
            if current_table is not None:
                tables.setdefault(current_table, [])
        elif line.startswith("%TR"):
            current_table = None
            headers = []
        elif line.startswith("%"):
            current_table = None
            headers = []
        elif current_table and not headers:
            headers = line.split("\t")
        elif current_table and headers:
            values = line.split("\t")
            row = dict(zip(headers, values, strict=False))
            tables[current_table].append(row)

    if "task" not in tables:
        raise ScheduleParseError("XER missing task table — file may be corrupt or unsupported version")

    schedule = ParsedSchedule(source_type="p6_xer")
    schedule.activities = tables.get("task", [])
    schedule.relationships = tables.get("taskpred", [])
    schedule.wbs = tables.get("projwbs", [])
    project_rows = tables.get("project", [])
    schedule.project_meta = project_rows[0] if project_rows else {}
    return schedule


def parse_p6_xml(content: str) -> ParsedSchedule:
    """Parse a Primavera P6 XML export."""

    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ScheduleParseError(f"Invalid XML: {exc}") from exc

    ns = {"p6": "http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects"}
    activities: list[dict[str, Any]] = []
    for activity in root.findall(".//p6:Activity", ns):
        activities.append(
            {
                "task_code": activity.findtext("p6:Id", "", ns),
                "task_name": activity.findtext("p6:Name", "", ns),
                "target_start_date": activity.findtext("p6:PlannedStartDate", "", ns),
                "target_end_date": activity.findtext("p6:PlannedFinishDate", "", ns),
            }
        )

    relationships: list[dict[str, Any]] = []
    for rel in root.findall(".//p6:Relationship", ns):
        relationships.append(
            {
                "pred_task_id": rel.findtext("p6:PredecessorActivityObjectId", "", ns),
                "task_id": rel.findtext("p6:SuccessorActivityObjectId", "", ns),
                "pred_type": rel.findtext("p6:Type", "FS", ns),
                "lag_hr_cnt": rel.findtext("p6:Lag", "0", ns),
            }
        )

    schedule = ParsedSchedule(source_type="p6_xml")
    schedule.activities = activities
    schedule.relationships = relationships
    return schedule
