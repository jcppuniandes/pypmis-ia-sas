"""Bounded P6 file exchange; no persistence, Scope mutation, calendars or CPM calculation.

Public contract:
parse_schedule_source(bytes, filename) -> source envelope and canonical snapshot.
validate_snapshot(snapshot) -> {errors, warnings, can_accept}; no mutations.
diff_schedule(previous_snapshot, incoming_snapshot) -> identity-based reconciliation.
export_schedule_xml(snapshot, *, baseline_reference=None) -> APIBusinessObjects XML bytes.

Numeric P6 durations, lags and float are retained as HOURS, never divided by 8.
Raw source fields/calendar definitions remain attached. The export is a declared
project-data subset, not native BaselineProject transport or proven P6 parity.
The installed Oracle p6apibo.xsd and an actual P6 application are not bundled.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.services.schedule_parser import ScheduleParseError
from app.services.schedule_parser import parse_xer as parse_legacy_xer

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_RECORDS = 50000
MAX_XML_DEPTH = 50
MAX_XER_TABLES = 128
MAX_XER_FIELDS = 512
P6_NAMESPACE = "http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects"
SUPPORTED_SUBSET = {
    "import": ["P6_XML_PROJECT_DATA_V1", "P6_XER_TABLES_V1", "LEGACY_XER_ADAPTER"],
    "export": ["P6_XML_PROJECT_DATA_V1"],
    "xer_export_supported": False,
    "native_baseline_transport_supported": False,
    "p6_application_roundtrip_verified": False,
    "cpm_calculated": False,
    "export_omissions": [
        "native BaselineProject transport",
        "XER opaque calendar encoding",
        "unknown source objects and fields",
        "project timezone metadata outside P6 flat project subset",
    ],
}
TABLES = {"PROJECT", "PROJWBS", "TASK", "TASKPRED", "CALENDAR", "ACTVTYPE", "ACTVCODE", "TASKACTV"}
RELATIONSHIP_TYPES = {
    "Finish to Start": "FS",
    "Start to Start": "SS",
    "Finish to Finish": "FF",
    "Start to Finish": "SF",
}
CONSTRAINTS = {
    "CS_MSO": "Mandatory Start",
    "CS_MEO": "Mandatory Finish",
    "CS_SO": "Start On",
    "CS_SOA": "Start On or After",
    "CS_SOB": "Start On or Before",
    "CS_FO": "Finish On",
    "CS_FOA": "Finish On or After",
    "CS_FOB": "Finish On or Before",
    "CS_ALAP": "As Late As Possible",
}
TYPES = {
    "TT_Task": "Task Dependent",
    "TT_Rsrc": "Resource Dependent",
    "TT_LOE": "Level of Effort",
    "TT_WBS": "WBS Summary",
    "TT_Mile": "Start Milestone",
    "TT_FinMile": "Finish Milestone",
}
STATUS = {"TK_NotStart": "Not Started", "TK_Active": "In Progress", "TK_Complete": "Completed"}
DATE_FIELDS = {
    "actual_start": ("ActualStartDate", "act_start_date"),
    "actual_finish": ("ActualFinishDate", "act_end_date"),
    "planned_start": ("PlannedStartDate", "target_start_date"),
    "planned_finish": ("PlannedFinishDate", "target_end_date"),
    "start": ("StartDate", "restart_date"),
    "finish": ("FinishDate", "reend_date"),
    "early_start": ("EarlyStartDate", "early_start_date"),
    "early_finish": ("EarlyFinishDate", "early_end_date"),
    "late_start": ("LateStartDate", "late_start_date"),
    "late_finish": ("LateFinishDate", "late_end_date"),
}


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _json_node(node: ET.Element) -> Any:
    if not len(node):
        return (node.text or "").strip()
    result: dict[str, Any] = {}
    for child in node:
        key, value = _name(child.tag), _json_node(child)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).isoformat()
    except ValueError:
        # Preserve the invalid literal for staging; validation must expose it.
        return str(value)


def _number(value: Any) -> float | None:
    # bool subclasses int in Python, but true/false are not source quantities.
    if isinstance(value, bool):
        return None
    if value in (None, ""):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if value in (True, "true", "True", "Y", "1", 1):
        return True
    if value in (False, "false", "False", "N", "0", 0):
        return False
    return None


def _pick(row: dict, *keys: str, default=""):
    return next((row[key] for key in keys if row.get(key) not in (None, "")), default)


def _snapshot() -> dict:
    return {
        "project": {},
        **{
            key: []
            for key in (
                "wbs",
                "activities",
                "calendars",
                "relationships",
                "constraints",
                "codes",
                "code_assignments",
                "external_links",
            )
        },
    }


def _activity(row: dict, *, xml: bool) -> dict:
    result = {
        "external_id": str(_pick(row, "ObjectId", "task_id")),
        "code": str(_pick(row, "Id", "task_code")),
        "name": _pick(row, "Name", "task_name"),
        "activity_type": _pick(row, "Type", "task_type"),
        "status": _pick(row, "Status", "status_code"),
        "wbs_external_id": str(_pick(row, "WBSObjectId", "wbs_id")),
        "calendar_external_id": str(_pick(row, "CalendarObjectId", "clndr_id")),
        "original_duration": _number(
            _pick(row, "PlannedDuration", "OriginalDuration", "target_drtn_hr_cnt", "orig_dur_hr_cnt")
        ),
        "remaining_duration": _number(_pick(row, "RemainingDuration", "remain_drtn_hr_cnt")),
        "duration_unit": "HOUR",
        "total_float": _number(_pick(row, "TotalFloat", "total_float_hr_cnt")),
        "free_float": _number(_pick(row, "FreeFloat", "free_float_hr_cnt")),
        "float_unit": "HOUR",
        # TASK.driving_path_flag is Longest Path, not an IsCritical field. Native
        # XER therefore leaves this nullable instead of inferring it from float.
        "critical": _bool(_pick(row, "IsCritical", "Critical")) if xml else None,
        "percent_complete_type": _pick(row, "PercentCompleteType", "complete_pct_type"),
        "percent_complete": _number(
            _pick(row, "PhysicalPercentComplete", "DurationPercentComplete", "PercentComplete", "phys_complete_pct")
        ),
        "cpm_source": "P6_IMPORTED",
        "progress_authority": False,
        "source_fields": deepcopy(row),
    }
    result["activity_type"] = TYPES.get(result["activity_type"], result["activity_type"])
    result["status"] = STATUS.get(result["status"], result["status"])
    result.update({key: _date(row.get(names[0 if xml else 1])) for key, names in DATE_FIELDS.items()})
    return result


def _relations(rows: list[dict], project_id: str) -> list[dict]:
    result = []
    for row in rows:
        kind = str(_pick(row, "Type", "pred_type"))
        result.append(
            {
                "external_id": str(_pick(row, "ObjectId", "task_pred_id")),
                "predecessor_external_id": str(_pick(row, "PredecessorActivityObjectId", "pred_task_id")),
                "successor_external_id": str(_pick(row, "SuccessorActivityObjectId", "task_id")),
                "relationship_type": RELATIONSHIP_TYPES.get(kind, kind.removeprefix("PR_")),
                "lag": _number(_pick(row, "Lag", "lag_hr_cnt")),
                "lag_unit": "HOUR",
                "predecessor_project_external_id": str(
                    _pick(row, "PredecessorProjectObjectId", "pred_proj_id", default=project_id)
                ),
                "successor_project_external_id": str(
                    _pick(row, "SuccessorProjectObjectId", "proj_id", default=project_id)
                ),
                "source_fields": deepcopy(row),
            }
        )
    return result


def _constraints(rows: list[dict], *, xml: bool) -> list[dict]:
    result = []
    for row in rows:
        identity = str(_pick(row, "ObjectId", "task_id"))
        for slot in (1, 2):
            kind = row.get(
                ("PrimaryConstraintType" if slot == 1 else "SecondaryConstraintType")
                if xml
                else ("cstr_type" if slot == 1 else "cstr_type2")
            )
            when = row.get(
                ("PrimaryConstraintDate" if slot == 1 else "SecondaryConstraintDate")
                if xml
                else ("cstr_date" if slot == 1 else "cstr_date2")
            )
            if kind:
                result.append(
                    {
                        "external_id": f"{identity}:{slot}",
                        "activity_external_id": identity,
                        "slot": slot,
                        "type": CONSTRAINTS.get(kind, kind),
                        "date": _date(when),
                        "source_fields": {"type": kind, "date": when},
                    }
                )
    return result


def _parse_xml(content: bytes) -> tuple[dict, list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ScheduleParseError("SCHEDULE_XML_UTF8_REQUIRED") from exc
    if "\x00" in text:
        raise ScheduleParseError("SCHEDULE_XML_UTF8_REQUIRED")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ScheduleParseError("SCHEDULE_XML_DTD_OR_ENTITY_FORBIDDEN")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ScheduleParseError("SCHEDULE_XML_INVALID") from exc
    if _name(root.tag) != "APIBusinessObjects":
        raise ScheduleParseError("SCHEDULE_XML_P6_CONTAINER_REQUIRED")
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    if not re.fullmatch(r"http://xmlns\.oracle\.com/Primavera/P6/V[0-9.]+/API/BusinessObjects", namespace):
        raise ScheduleParseError("SCHEDULE_XML_P6_NAMESPACE_UNSUPPORTED")
    stack, count = [(root, 0)], 0
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > MAX_RECORDS * 30 or depth > MAX_XML_DEPTH:
            raise ScheduleParseError("SCHEDULE_XML_STRUCTURE_LIMIT")
        stack.extend((child, depth + 1) for child in element)
    groups: dict[str, list[dict]] = {}
    for element in root.iter():
        local = _name(element.tag)
        if local in {
            "Project",
            "WBS",
            "Activity",
            "Calendar",
            "Relationship",
            "ActivityCodeType",
            "ActivityCode",
            "ActivityCodeAssignment",
        }:
            if len(groups.setdefault(local, [])) >= MAX_RECORDS:
                raise ScheduleParseError("SCHEDULE_RECORD_LIMIT")
            value = _json_node(element)
            if not isinstance(value, dict):
                raise ScheduleParseError("SCHEDULE_XML_BUSINESS_OBJECT_FIELDS_REQUIRED")
            nested = {
                "Project",
                "WBS",
                "Activity",
                "Calendar",
                "Relationship",
                "ActivityCodeType",
                "ActivityCode",
                "ActivityCodeAssignment",
                "StandardWorkWeek",
                "HolidayOrExceptions",
                "Shifts",
            }
            if any(
                count > 1 for key, count in Counter(_name(child.tag) for child in element).items() if key not in nested
            ):
                raise ScheduleParseError("SCHEDULE_XML_DUPLICATE_SCALAR_FIELD")
            groups[local].append(value)
    if len(groups.get("Project", [])) != 1:
        raise ScheduleParseError("SCHEDULE_SINGLE_P6_PROJECT_REQUIRED")
    snapshot = _from_rows(groups, xml=True)
    known = {
        "Project",
        "WBS",
        "Activity",
        "Calendar",
        "Relationship",
        "ActivityCodeType",
        "ActivityCode",
        "ActivityCodeAssignment",
    }
    unsupported = sorted({_name(element.tag) for element in root if _name(element.tag) not in known})
    return snapshot, unsupported


def _native_xer_tables(content: bytes) -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Explicit lossless Windows-1252 fallback, never errors=ignore.
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise ScheduleParseError("SCHEDULE_XER_ENCODING_UNSUPPORTED") from exc
    if "\x00" in text:
        raise ScheduleParseError("SCHEDULE_XER_BINARY_FORBIDDEN")
    if text.lstrip().startswith("%FMT:"):
        legacy = parse_legacy_xer(text)
        return {
            "PROJECT": [legacy.project_meta],
            "TASK": legacy.activities,
            "PROJWBS": legacy.wbs,
            "TASKPRED": legacy.relationships,
        }
    tables, table, fields, ended, record_count = {}, "", [], False, 0
    if not text.startswith("ERMHDR\t"):
        raise ScheduleParseError("SCHEDULE_XER_HEADER_INVALID")
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        if ended:
            raise ScheduleParseError("SCHEDULE_XER_TRAILING_RECORDS_AFTER_END")
        parts = line.split("\t")
        marker = parts[0]
        if marker == "%T" and len(parts) == 2:
            table, fields = parts[1].upper(), []
            if table in tables:
                raise ScheduleParseError("SCHEDULE_XER_DUPLICATE_TABLE")
            if len(tables) >= MAX_XER_TABLES:
                raise ScheduleParseError("SCHEDULE_XER_TABLE_LIMIT")
            tables[table] = []
        elif marker == "%F" and table:
            fields = [value.lower() for value in parts[1:]]
            if not fields or len(fields) > MAX_XER_FIELDS or len(set(fields)) != len(fields):
                raise ScheduleParseError("SCHEDULE_XER_INVALID_FIELDS")
        elif marker == "%R" and table and fields:
            if len(parts) - 1 != len(fields):
                raise ScheduleParseError(f"SCHEDULE_XER_ROW_WIDTH_INVALID:{line_number}")
            tables[table].append(dict(zip(fields, parts[1:], strict=True)))
            record_count += 1
            if record_count > MAX_RECORDS:
                raise ScheduleParseError("SCHEDULE_RECORD_LIMIT")
        elif marker == "%E":
            ended = True
        elif marker != "ERMHDR":
            raise ScheduleParseError(f"SCHEDULE_XER_RECORD_INVALID:{line_number}")
    if not ended or "TASK" not in tables:
        raise ScheduleParseError("SCHEDULE_XER_INCOMPLETE_OR_TASK_TABLE_MISSING")
    return tables


def _from_rows(groups: dict, *, xml: bool) -> dict:
    snapshot = _snapshot()
    project = groups["Project" if xml else "PROJECT"][0]
    project_id = str(_pick(project, "ObjectId", "proj_id"))
    snapshot["project"] = {
        "external_id": project_id,
        "code": _pick(project, "Id", "proj_short_name"),
        "name": _pick(project, "Name", "proj_name", "proj_short_name"),
        "data_date": _date(_pick(project, "DataDate", "last_recalc_date", "data_date", default=None)),
        "timezone": _pick(project, "TimeZone", "timezone", default="UNKNOWN"),
        "calendar_basis": _pick(project, "ActivityDefaultCalendarObjectId", "clndr_id", default="UNKNOWN"),
        "source_fields": deepcopy(project),
    }
    for row in groups.get("WBS" if xml else "PROJWBS", []):
        snapshot["wbs"].append(
            {
                "external_id": str(_pick(row, "ObjectId", "wbs_id")),
                "code": _pick(row, "Code", "wbs_short_name"),
                "name": _pick(row, "Name", "wbs_name"),
                "parent_external_id": str(_pick(row, "ParentObjectId", "parent_wbs_id")),
                "path": "",
                "sort_order": _number(_pick(row, "SequenceNumber", "seq_num")),
                "status": "IMPORTED",
                "source_fields": deepcopy(row),
            }
        )
    activity_rows = groups.get("Activity" if xml else "TASK", [])
    snapshot["activities"] = [_activity(row, xml=xml) for row in activity_rows]
    snapshot["constraints"] = _constraints(activity_rows, xml=xml)
    snapshot["relationships"] = _relations(groups.get("Relationship" if xml else "TASKPRED", []), project_id)
    for row in groups.get("Calendar" if xml else "CALENDAR", []):
        snapshot["calendars"].append(
            {
                "external_id": str(_pick(row, "ObjectId", "clndr_id")),
                "name": _pick(row, "Name", "clndr_name"),
                "type": {"CA_Project": "Project", "CA_Base": "Global", "CA_Rsrc": "Resource"}.get(
                    _pick(row, "Type", "clndr_type"), _pick(row, "Type", "clndr_type")
                ),
                "hours_per_day": _number(_pick(row, "HoursPerDay", "day_hr_cnt")),
                "workweek": deepcopy(row.get("StandardWorkWeek")),
                "shifts": deepcopy(row.get("Shifts")),
                "holidays": deepcopy(row.get("HolidayOrExceptions")),
                "exceptions": deepcopy(row.get("HolidayOrExceptions")),
                "timezone": _pick(row, "TimeZone", "timezone", default="UNKNOWN"),
                "source": "P6_IMPORTED",
                "opaque_calendar_data": row.get("clndr_data"),
                "source_fields": deepcopy(row),
            }
        )
    for key, kind in (
        ("ActivityCodeType" if xml else "ACTVTYPE", "TYPE"),
        ("ActivityCode" if xml else "ACTVCODE", "VALUE"),
    ):
        for row in groups.get(key, []):
            snapshot["codes"].append(
                {
                    "external_id": str(
                        _pick(row, "ObjectId", "actv_code_type_id" if kind == "TYPE" else "actv_code_id")
                    ),
                    "kind": kind,
                    "parent_external_id": str(_pick(row, "CodeTypeObjectId", "actv_code_type_id"))
                    if kind == "VALUE"
                    else "",
                    "name": _pick(row, "Name", "actv_code_type", "actv_code_name"),
                    "code": _pick(row, "CodeValue", "short_name"),
                    "source_fields": deepcopy(row),
                }
            )
    for row in groups.get("ActivityCodeAssignment" if xml else "TASKACTV", []):
        snapshot["code_assignments"].append(
            {
                "activity_external_id": str(_pick(row, "ActivityObjectId", "task_id")),
                "type_external_id": str(_pick(row, "ActivityCodeTypeObjectId", "actv_code_type_id")),
                "value_external_id": str(_pick(row, "ActivityCodeObjectId", "actv_code_id")),
                "source_fields": deepcopy(row),
            }
        )
    activity_ids = {row["external_id"] for row in snapshot["activities"]}
    for row in snapshot["relationships"]:
        cross_project = any(
            row[key] and row[key] != project_id
            for key in ("predecessor_project_external_id", "successor_project_external_id")
        )
        unresolved = any(row[key] not in activity_ids for key in ("predecessor_external_id", "successor_external_id"))
        row["is_external"] = cross_project or unresolved
        row["resolution"] = "EXTERNAL_PROJECT" if cross_project else "UNRESOLVED" if unresolved else "INTERNAL"
        if row["is_external"]:
            snapshot["external_links"].append(deepcopy(row))
    by_id = {row["external_id"]: row for row in snapshot["wbs"]}
    for row in snapshot["wbs"]:
        current, visited, path = row, set(), []
        while current and current["external_id"] not in visited:
            if len(visited) >= MAX_XML_DEPTH:
                raise ScheduleParseError("SCHEDULE_WBS_DEPTH_LIMIT")
            visited.add(current["external_id"])
            path.append(current["code"] or current["external_id"])
            current = by_id.get(current.get("parent_external_id"))
        row["path"] = "/".join(reversed(path))
    return snapshot


def validate_snapshot(snapshot: dict) -> dict:
    """Structural/source validation only; scoped mapping and health policy live in service."""
    errors, warnings = [], []
    if not isinstance(snapshot, dict):
        return {"errors": ["SNAPSHOT_OBJECT_REQUIRED"], "warnings": [], "can_accept": False, "cpm_calculated": False}
    project = snapshot.get("project", {})
    if not isinstance(project, dict):
        return {"errors": ["PROJECT_OBJECT_REQUIRED"], "warnings": [], "can_accept": False, "cpm_calculated": False}
    if not project.get("external_id"):
        errors.append("PROJECT_ID_REQUIRED")
    if not project.get("data_date"):
        errors.append("DATA_DATE_REQUIRED")
    elif _valid_date(project["data_date"]) is False:
        errors.append("DATA_DATE_INVALID")
    indexes = {}
    for key in ("wbs", "activities", "calendars", "relationships"):
        rows = snapshot.get(key, [])
        if not isinstance(rows, list) or len(rows) > MAX_RECORDS or any(not isinstance(row, dict) for row in rows):
            errors.append(f"{key.upper()}_STRUCTURE_INVALID")
            indexes[key] = set()
            continue
        identities = [str(row.get("external_id") or "") for row in rows]
        indexes[key] = set(identities)
        if any(not identity for identity in identities):
            errors.append(f"{key.upper()}_ID_REQUIRED")
        if any(count > 1 for count in Counter(identities).values()):
            errors.append(f"{key.upper()}_DUPLICATE_ID")
    for key in ("constraints", "codes", "code_assignments", "external_links"):
        rows = snapshot.get(key, [])
        if not isinstance(rows, list) or len(rows) > MAX_RECORDS or any(not isinstance(row, dict) for row in rows):
            errors.append(f"{key.upper()}_STRUCTURE_INVALID")
    if any("STRUCTURE_INVALID" in error for error in errors):
        return {"errors": sorted(set(errors)), "warnings": [], "can_accept": False, "cpm_calculated": False}
    # Draft/successor snapshots are untrusted JSON, not necessarily parser output.
    # Reject non-scalar identities/labels before sets, indexing, or set membership
    # can raise TypeError. Do not coerce an object/list identity into a valid ID.
    text_keys = {
        "external_id",
        "parent_external_id",
        "code",
        "name",
        "activity_type",
        "status",
        "path",
        "wbs_external_id",
        "calendar_external_id",
        "duration_unit",
        "float_unit",
        "percent_complete_type",
        "predecessor_external_id",
        "successor_external_id",
        "predecessor_project_external_id",
        "successor_project_external_id",
        "relationship_type",
        "lag_unit",
        "resolution",
        "activity_external_id",
        "type",
        "kind",
        "date",
        "type_external_id",
        "value_external_id",
        "timezone",
        "source",
        "data_date",
        "calendar_basis",
        *DATE_FIELDS,
    }
    objects = [project] + [row for key in _snapshot() if key != "project" for row in snapshot.get(key, [])]
    for row in objects:
        if any(value is not None and not isinstance(value, str) for key, value in row.items() if key in text_keys):
            errors.append("SNAPSHOT_TEXT_FIELD_INVALID")
        if "source_fields" in row and not isinstance(row["source_fields"], dict):
            errors.append("SNAPSHOT_SOURCE_FIELDS_OBJECT_REQUIRED")
    if "SNAPSHOT_TEXT_FIELD_INVALID" in errors or "SNAPSHOT_SOURCE_FIELDS_OBJECT_REQUIRED" in errors:
        return {"errors": sorted(set(errors)), "warnings": [], "can_accept": False, "cpm_calculated": False}
    if not snapshot.get("activities"):
        errors.append("ACTIVITIES_REQUIRED")
    for key in ("wbs", "activities"):
        codes = [row.get("code") for row in snapshot.get(key, [])]
        if any(not code for code in codes) or len(set(codes)) != len(codes):
            errors.append(f"{key.upper()}_CODE_MISSING_OR_DUPLICATE")
    by_id = {row.get("external_id"): row for row in snapshot.get("wbs", [])}
    for row in snapshot.get("wbs", []):
        parent, visited = row.get("parent_external_id"), {row.get("external_id")}
        while parent:
            if len(visited) >= MAX_XML_DEPTH:
                errors.append("WBS_HIERARCHY_DEPTH_LIMIT")
                break
            if parent in visited:
                errors.append("WBS_HIERARCHY_CYCLE")
                break
            visited.add(parent)
            if parent not in by_id:
                errors.append("WBS_PARENT_UNRESOLVED")
                break
            parent = by_id[parent].get("parent_external_id")
    for row in snapshot.get("activities", []):
        if "activity_type" in row and row["activity_type"] is None:
            errors.append("ACTIVITY_TYPE_REQUIRED")
        if row.get("wbs_external_id") not in indexes["wbs"]:
            errors.append("ACTIVITY_WBS_UNRESOLVED")
        if row.get("calendar_external_id") not in indexes["calendars"]:
            warnings.append("ACTIVITY_CALENDAR_MISSING")
        for key in DATE_FIELDS:
            if row.get(key) and not _valid_date(row[key]):
                errors.append("ACTIVITY_DATE_INVALID")
        if row.get("duration_unit") not in {"HOUR", "DAY", "UNKNOWN"}:
            errors.append("DURATION_UNIT_UNSUPPORTED")
        if row.get("critical") is not None and not isinstance(row["critical"], bool):
            errors.append("IMPORTED_CRITICALITY_BOOLEAN_REQUIRED")
        if (
            row.get("percent_complete") is not None
            and _number(row["percent_complete"]) is not None
            and not 0 <= float(row["percent_complete"]) <= 100
        ):
            errors.append("IMPORTED_PERCENT_COMPLETE_OUT_OF_RANGE")
        for key in ("original_duration", "remaining_duration", "total_float", "free_float", "percent_complete"):
            number = row.get(key)
            if number is not None and (_number(number) is None or isinstance(number, bool)):
                errors.append("ACTIVITY_NUMBER_INVALID")
        if any(
            row.get(key) is not None and (_number(row[key]) or 0) < 0
            for key in ("original_duration", "remaining_duration")
        ):
            errors.append("DURATION_NEGATIVE")
        raw = row.get("source_fields", {})
        for keys in (
            ("OriginalDuration", "PlannedDuration", "target_drtn_hr_cnt", "orig_dur_hr_cnt"),
            ("RemainingDuration", "remain_drtn_hr_cnt"),
            ("TotalFloat", "total_float_hr_cnt"),
            ("FreeFloat", "free_float_hr_cnt"),
            ("PhysicalPercentComplete", "phys_complete_pct"),
        ):
            literal = _pick(raw, *keys, default=None)
            if literal is not None and _number(literal) is None:
                errors.append("SOURCE_NUMBER_INVALID")
        if row.get("total_float") is None:
            warnings.append("IMPORTED_FLOAT_UNKNOWN")
        if row.get("critical") is None:
            warnings.append("IMPORTED_CRITICALITY_UNKNOWN")
    for row in snapshot.get("calendars", []):
        literal = _pick(row.get("source_fields", {}), "HoursPerDay", "day_hr_cnt", default=None)
        if literal is not None and _number(literal) is None:
            errors.append("SOURCE_CALENDAR_HOURS_INVALID")
        if row.get("hours_per_day") is None:
            warnings.append("CALENDAR_HOURS_PER_DAY_UNKNOWN_NO_CONVERSION")
        elif (
            isinstance(row["hours_per_day"], bool)
            or _number(row["hours_per_day"]) is None
            or not 0 < float(row["hours_per_day"]) <= 24
        ):
            errors.append("CALENDAR_HOURS_PER_DAY_INVALID")
        if row.get("opaque_calendar_data") and not row.get("workweek"):
            warnings.append("XER_CALENDAR_DEFINITION_OPAQUE_PRESERVED")
    for row in snapshot.get("relationships", []):
        if row.get("relationship_type") not in {"FS", "SS", "FF", "SF"}:
            errors.append("RELATIONSHIP_TYPE_UNSUPPORTED")
        if row.get("lag") is not None and _number(row["lag"]) is None:
            errors.append("RELATIONSHIP_LAG_INVALID")
        literal = _pick(row.get("source_fields", {}), "Lag", "lag_hr_cnt", default=None)
        if literal is not None and _number(literal) is None:
            errors.append("RELATIONSHIP_SOURCE_LAG_INVALID")
        if (
            row.get("is_external")
            or row.get("predecessor_external_id") not in indexes["activities"]
            or row.get("successor_external_id") not in indexes["activities"]
        ):
            warnings.append("EXTERNAL_OR_UNRESOLVED_RELATIONSHIP")
    for row in snapshot.get("constraints", []):
        if row.get("activity_external_id") not in indexes["activities"]:
            errors.append("CONSTRAINT_ACTIVITY_UNRESOLVED")
        if row.get("type") not in set(CONSTRAINTS.values()):
            warnings.append("CONSTRAINT_TYPE_OUTSIDE_SUPPORTED_SUBSET")
        if row.get("date") and not _valid_date(row["date"]):
            errors.append("CONSTRAINT_DATE_INVALID")
    values = {row.get("external_id") for row in snapshot.get("codes", []) if row.get("kind") == "VALUE"}
    types = {row.get("external_id") for row in snapshot.get("codes", []) if row.get("kind") == "TYPE"}
    for row in snapshot.get("code_assignments", []):
        if (
            row.get("activity_external_id") not in indexes["activities"]
            or row.get("type_external_id") not in types
            or row.get("value_external_id") not in values
        ):
            errors.append("ACTIVITY_CODE_ASSIGNMENT_UNRESOLVED")
    return {
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "can_accept": not errors,
        "cpm_calculated": False,
    }


def _valid_date(value) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


def parse_schedule_source(content: bytes, filename: str) -> dict:
    if not content or len(content) > MAX_SOURCE_BYTES:
        raise ScheduleParseError("SCHEDULE_SOURCE_EMPTY_OR_SIZE_LIMIT")
    suffix = Path(filename).suffix.lower()
    if suffix == ".xml":
        snapshot, unsupported = _parse_xml(content)
        source_format = "P6_XML"
    elif suffix == ".xer":
        groups = _native_xer_tables(content)
        if len(groups.get("PROJECT", [])) != 1:
            raise ScheduleParseError("SCHEDULE_SINGLE_P6_PROJECT_REQUIRED")
        snapshot, unsupported = _from_rows(groups, xml=False), sorted(set(groups) - TABLES)
        source_format = "P6_XER"
    else:
        raise ScheduleParseError("SCHEDULE_SOURCE_FORMAT_UNSUPPORTED")
    validation = validate_snapshot(snapshot)
    unsupported.extend(_unsupported_source_fields(snapshot))
    if unsupported:
        validation["warnings"].append("UNSUPPORTED_SOURCE_OBJECTS_RETAINED_IN_ORIGINAL_FILE")
    return {
        "snapshot": snapshot,
        "validation": validation,
        "source_hash": hashlib.sha256(content).hexdigest(),
        "source_format": source_format,
        "supported_subset": deepcopy(SUPPORTED_SUBSET),
        "unsupported_fields": unsupported,
    }


def _unsupported_source_fields(snapshot: dict) -> list[str]:
    allowed = {
        "project": {
            "ObjectId",
            "Id",
            "Name",
            "DataDate",
            "TimeZone",
            "ActivityDefaultCalendarObjectId",
            "proj_id",
            "proj_short_name",
            "proj_name",
            "last_recalc_date",
            "data_date",
            "timezone",
            "clndr_id",
        },
        "wbs": {
            "ObjectId",
            "Code",
            "Name",
            "ParentObjectId",
            "SequenceNumber",
            "ProjectObjectId",
            "wbs_id",
            "wbs_short_name",
            "wbs_name",
            "parent_wbs_id",
            "seq_num",
            "proj_id",
        },
        "activities": {
            "ObjectId",
            "Id",
            "Name",
            "Type",
            "Status",
            "ProjectObjectId",
            "WBSObjectId",
            "CalendarObjectId",
            "PlannedDuration",
            "OriginalDuration",
            "RemainingDuration",
            "TotalFloat",
            "FreeFloat",
            "IsCritical",
            "Critical",
            "PercentCompleteType",
            "PhysicalPercentComplete",
            "DurationPercentComplete",
            "PercentComplete",
            "PrimaryConstraintType",
            "PrimaryConstraintDate",
            "SecondaryConstraintType",
            "SecondaryConstraintDate",
            "task_id",
            "task_code",
            "task_name",
            "task_type",
            "status_code",
            "wbs_id",
            "clndr_id",
            "proj_id",
            "target_drtn_hr_cnt",
            "orig_dur_hr_cnt",
            "remain_drtn_hr_cnt",
            "total_float_hr_cnt",
            "free_float_hr_cnt",
            "complete_pct_type",
            "phys_complete_pct",
            "cstr_type",
            "cstr_date",
            "cstr_type2",
            "cstr_date2",
            *[name for names in DATE_FIELDS.values() for name in names],
        },
        "calendars": {
            "ObjectId",
            "Name",
            "Type",
            "HoursPerDay",
            "ProjectObjectId",
            "StandardWorkWeek",
            "HolidayOrExceptions",
            "TimeZone",
            "Shifts",
            "clndr_id",
            "clndr_name",
            "clndr_type",
            "day_hr_cnt",
            "clndr_data",
            "proj_id",
            "timezone",
        },
        "relationships": {
            "ObjectId",
            "PredecessorActivityObjectId",
            "SuccessorActivityObjectId",
            "Type",
            "Lag",
            "PredecessorProjectObjectId",
            "SuccessorProjectObjectId",
            "task_pred_id",
            "pred_task_id",
            "task_id",
            "pred_type",
            "lag_hr_cnt",
            "pred_proj_id",
            "proj_id",
        },
    }
    unsupported = []
    for collection, fields in allowed.items():
        rows = [snapshot["project"]] if collection == "project" else snapshot[collection]
        unsupported.extend(
            f"{collection}.{key}" for row in rows for key in row.get("source_fields", {}) if key not in fields
        )
    return sorted(set(unsupported))


def diff_schedule(previous: dict | None, incoming: dict) -> dict:
    previous = previous or _snapshot()
    result = {}
    for collection in (
        "wbs",
        "activities",
        "calendars",
        "relationships",
        "constraints",
        "codes",
        "code_assignments",
        "external_links",
    ):

        def identity(row):
            return str(row.get("external_id") or json.dumps(row, sort_keys=True))

        before = {identity(row): row for row in previous.get(collection, [])}
        after = {identity(row): row for row in incoming.get(collection, [])}
        changed = []
        for key in sorted(before.keys() & after.keys()):
            fields = sorted(
                name
                for name in set(before[key]) | set(after[key])
                if name != "source_fields" and before[key].get(name) != after[key].get(name)
            )
            if fields:
                changed.append(
                    {
                        "external_id": key,
                        "fields": fields,
                        "before": deepcopy(before[key]),
                        "after": deepcopy(after[key]),
                    }
                )
        result[collection] = {
            "added": sorted(after.keys() - before.keys()),
            "removed": sorted(before.keys() - after.keys()),
            "changed": changed,
        }
    old_project, new_project = previous.get("project", {}), incoming.get("project", {})
    result["data_date"] = {
        "before": old_project.get("data_date"),
        "after": new_project.get("data_date"),
        "changed": old_project.get("data_date") != new_project.get("data_date"),
    }
    result["project_metadata_changed"] = sorted(
        key
        for key in set(old_project) | set(new_project)
        if key != "source_fields" and old_project.get(key) != new_project.get(key)
    )
    result["mapping_impacts"] = {
        key: {"removed": result[key]["removed"], "changed": [row["external_id"] for row in result[key]["changed"]]}
        for key in ("wbs", "activities")
    }
    result["cpm_calculated"] = False
    return result


def _put(parent: ET.Element, key: str, value: Any):
    if value not in (None, "", "UNKNOWN"):
        ET.SubElement(parent, key).text = str(value).lower() if isinstance(value, bool) else str(value)


def _put_structure(parent: ET.Element, key: str, value: Any):
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _put_structure(parent, key, item)
    elif isinstance(value, dict):
        node = ET.SubElement(parent, key)
        for child, item in value.items():
            _put_structure(node, child, item)
    else:
        ET.SubElement(parent, key).text = str(value)


def export_schedule_xml(snapshot: dict, *, baseline_reference: dict | None = None) -> bytes:
    """Export only documented P6 project-data fields; baseline reference stays in manifest.

    Native BaselineProject transport and XER export are intentionally unsupported.
    Unknown calendars/units or unsupported constraints block this safe export subset.
    """
    validation = validate_snapshot(snapshot)
    if validation["errors"]:
        raise ScheduleParseError("SCHEDULE_EXPORT_INVALID_SNAPSHOT:" + ",".join(validation["errors"]))
    for collection in ("wbs", "activities", "calendars", "relationships", "codes"):
        if any(
            not re.fullmatch(r"[1-9][0-9]*", str(row.get("external_id", ""))) for row in snapshot.get(collection, [])
        ):
            raise ScheduleParseError("SCHEDULE_XML_EXPORT_POSITIVE_INTEGER_OBJECT_IDS_REQUIRED")
    if not re.fullmatch(r"[1-9][0-9]*", str(snapshot["project"].get("external_id", ""))):
        raise ScheduleParseError("SCHEDULE_XML_EXPORT_POSITIVE_INTEGER_PROJECT_ID_REQUIRED")
    if any(
        row.get("duration_unit") != "HOUR" or row.get("float_unit") not in {None, "HOUR"}
        for row in snapshot["activities"]
    ):
        raise ScheduleParseError("SCHEDULE_XML_EXPORT_HOUR_UNITS_REQUIRED_NO_CONVERSION")
    if any(row.get("opaque_calendar_data") and not row.get("workweek") for row in snapshot["calendars"]):
        raise ScheduleParseError("SCHEDULE_XER_OPAQUE_CALENDAR_CANNOT_EXPORT_XML_LOSSLESSLY")
    if any(row.get("type") not in {"Project", "Global", "Resource"} for row in snapshot["calendars"]):
        raise ScheduleParseError("SCHEDULE_XML_EXPORT_CALENDAR_TYPE_UNSUPPORTED")
    if any(row.get("type") not in set(CONSTRAINTS.values()) for row in snapshot.get("constraints", [])):
        raise ScheduleParseError("SCHEDULE_XML_EXPORT_CONSTRAINT_TYPE_UNSUPPORTED")
    root = ET.Element("APIBusinessObjects", xmlns=P6_NAMESPACE)
    project = snapshot["project"]
    node = ET.SubElement(root, "Project")
    for field, key in (
        ("ObjectId", "external_id"),
        ("Id", "code"),
        ("Name", "name"),
        ("DataDate", "data_date"),
        ("ActivityDefaultCalendarObjectId", "calendar_basis"),
    ):
        _put(node, field, project.get(key))
    for row in snapshot["calendars"]:
        node = ET.SubElement(root, "Calendar")
        for field, key in (
            ("ObjectId", "external_id"),
            ("Name", "name"),
            ("Type", "type"),
            ("HoursPerDay", "hours_per_day"),
        ):
            _put(node, field, row.get(key))
        _put_structure(node, "StandardWorkWeek", row.get("workweek"))
        _put_structure(node, "HolidayOrExceptions", row.get("exceptions") or row.get("holidays"))
    for row in snapshot["wbs"]:
        node = ET.SubElement(root, "WBS")
        _put(node, "ProjectObjectId", project["external_id"])
        for field, key in (
            ("ObjectId", "external_id"),
            ("Code", "code"),
            ("Name", "name"),
            ("ParentObjectId", "parent_external_id"),
            ("SequenceNumber", "sort_order"),
        ):
            _put(node, field, row.get(key))
    for row in snapshot["activities"]:
        node = ET.SubElement(root, "Activity")
        _put(node, "ProjectObjectId", project["external_id"])
        for field, key in (
            ("ObjectId", "external_id"),
            ("Id", "code"),
            ("Name", "name"),
            ("Type", "activity_type"),
            ("Status", "status"),
            ("WBSObjectId", "wbs_external_id"),
            ("CalendarObjectId", "calendar_external_id"),
            ("PlannedDuration", "original_duration"),
            ("RemainingDuration", "remaining_duration"),
            ("TotalFloat", "total_float"),
            ("FreeFloat", "free_float"),
            ("IsCritical", "critical"),
            ("PercentCompleteType", "percent_complete_type"),
            ("PhysicalPercentComplete", "percent_complete"),
        ):
            _put(node, field, row.get(key))
        for key, (field, _) in DATE_FIELDS.items():
            _put(node, field, row.get(key))
        for constraint in snapshot.get("constraints", []):
            if constraint.get("activity_external_id") == row["external_id"]:
                prefix = "Secondary" if constraint.get("slot") == 2 else "Primary"
                _put(node, prefix + "ConstraintType", constraint.get("type"))
                _put(node, prefix + "ConstraintDate", constraint.get("date"))
    reverse_rel = {value: key for key, value in RELATIONSHIP_TYPES.items()}
    for row in snapshot["relationships"]:
        node = ET.SubElement(root, "Relationship")
        for field, key in (
            ("ObjectId", "external_id"),
            ("PredecessorActivityObjectId", "predecessor_external_id"),
            ("SuccessorActivityObjectId", "successor_external_id"),
            ("PredecessorProjectObjectId", "predecessor_project_external_id"),
            ("SuccessorProjectObjectId", "successor_project_external_id"),
            ("Lag", "lag"),
        ):
            _put(node, field, row.get(key))
        _put(node, "Type", reverse_rel[row["relationship_type"]])
    for row in snapshot.get("codes", []):
        node = ET.SubElement(root, "ActivityCodeType" if row["kind"] == "TYPE" else "ActivityCode")
        _put(node, "ObjectId", row["external_id"])
        _put(node, "Name", row.get("name"))
        if row["kind"] == "VALUE":
            _put(node, "CodeTypeObjectId", row.get("parent_external_id"))
            _put(node, "CodeValue", row.get("code"))
    for row in snapshot.get("code_assignments", []):
        node = ET.SubElement(root, "ActivityCodeAssignment")
        for field, key in (
            ("ActivityObjectId", "activity_external_id"),
            ("ActivityCodeTypeObjectId", "type_external_id"),
            ("ActivityCodeObjectId", "value_external_id"),
        ):
            _put(node, field, row.get(key))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
