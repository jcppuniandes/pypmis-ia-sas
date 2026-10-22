"""Pure 4D semantic projection of imported dates, never a scheduling engine.

Missing or ambiguous temporal mappings stay UNKNOWN. Imported physical progress is
shown separately: a playback COMPLETED class is a date projection, not certification.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

NATURES = {"INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"}
PHASES = {"EXECUTE", "INSTALL", "USE", "REMOVE"}


def instant(value, timezone_name="UTC"):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(UTC)


def activity_dates(activity, *, baseline=False, timezone_name="UTC"):
    """Read actual/current or baseline-planned dates; never infer missing duration."""
    if baseline:
        start = activity.get("planned_start") or activity.get("start")
        finish = activity.get("planned_finish") or activity.get("finish")
    else:
        start = activity.get("actual_start") or activity.get("start") or activity.get("planned_start")
        finish = activity.get("actual_finish") or activity.get("finish") or activity.get("planned_finish")
    # A declared milestone has one source instant, not a fabricated duration.
    kind = str(activity.get("activity_type", ""))
    if "Milestone" in kind:
        start = start or finish
        finish = finish or start
    return instant(start, timezone_name), instant(finish, timezone_name)


def near_critical(activity, threshold):
    value = activity.get("total_float")
    if value is None or activity.get("float_unit") != threshold.get("unit"):
        return None
    try:
        parsed = Decimal(str(value))
        return parsed <= Decimal(str(threshold["value"])) if parsed.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def resolve_state(
    nature, activities, at, *, baseline=False, threshold=None, blocked=False, timezone_name="UTC", data_date=None
):
    """Resolve an explicit M:N temporal membership without changing any source."""
    selected = instant(at, timezone_name)
    if selected is None:
        raise ValueError("4D selected date is required")
    issues = []
    intervals = []
    for activity in activities:
        try:
            start, finish = activity_dates(activity, baseline=baseline, timezone_name=timezone_name)
        except (TypeError, ValueError):
            start, finish = None, None
        phase = activity.get("phase", "EXECUTE")
        if phase not in PHASES:
            issues.append("ACTIVITY_PHASE_INVALID")
        if start is None or finish is None:
            issues.append("ACTIVITY_DATES_INCOMPLETE")
        elif finish < start:
            issues.append("ACTIVITY_DATE_ORDER_INVALID")
        else:
            intervals.append((phase, start, finish))
    if nature not in NATURES:
        issues.append("SCOPE_NATURE_INVALID")
    if not activities:
        issues.append("ACTIVITY_MAPPING_REQUIRED")
    state, semantic, visible = "UNKNOWN", "UNKNOWN", True
    if nature == "TEMPORARY":
        install = [(start, finish) for phase, start, finish in intervals if phase == "INSTALL"]
        remove = [(start, finish) for phase, start, finish in intervals if phase == "REMOVE"]
        use = [(start, finish) for phase, start, finish in intervals if phase == "USE"]
        if not install or not remove:
            issues.append("TEMPORARY_INSTALL_REMOVE_PHASES_REQUIRED")
        elif any(phase == "EXECUTE" for phase, _, _ in intervals):
            issues.append("TEMPORARY_EXPLICIT_PHASE_REQUIRED")
        else:
            first_install = min(start for start, _ in install)
            installed = max(finish for _, finish in install)
            removal_start = min(start for start, _ in remove)
            removed = max(finish for _, finish in remove)
            if installed > removal_start or any(start < installed or finish > removal_start for start, finish in use):
                issues.append("TEMPORARY_PHASE_ORDER_INVALID")
            elif not issues:
                if selected < first_install:
                    state, semantic, visible = "NOT_STARTED", "ABSENT_BEFORE_INSTALL", False
                elif selected < installed:
                    state, semantic = "IN_PROGRESS", "TEMPORARY_INSTALLATION"
                elif selected < removal_start:
                    state, semantic = "TEMPORARY", "TEMPORARY_IN_USE"
                elif selected < removed:
                    state, semantic = "IN_PROGRESS", "TEMPORARY_REMOVAL"
                else:
                    state, semantic, visible = "REMOVED", "ABSENT_AFTER_REMOVAL", False
    elif intervals and not issues:
        start = min(start for _, start, _ in intervals)
        finish = max(finish for _, _, finish in intervals)
        stage = "BEFORE" if selected < start else "DURING" if selected < finish else "AFTER"
        if nature == "INSTALL":
            state, semantic, visible = {
                "BEFORE": ("NOT_STARTED", "FUTURE_NOT_INSTALLED", False),
                "DURING": ("IN_PROGRESS", "INSTALLATION", True),
                "AFTER": ("COMPLETED", "INSTALLED", True),
            }[stage]
        elif nature == "REMOVE":
            state, semantic, visible = {
                "BEFORE": ("NOT_STARTED", "EXISTING", True),
                "DURING": ("IN_PROGRESS", "REMOVAL", True),
                "AFTER": ("REMOVED", "REMOVED", False),
            }[stage]
        elif nature == "MAINTENANCE":
            state, semantic, visible = {
                "BEFORE": ("NOT_STARTED", "EXISTING_IN_SERVICE", True),
                "DURING": ("MAINTENANCE", "MAINTENANCE_INTERVENTION", True),
                "AFTER": ("COMPLETED", "RESTORED_IN_SERVICE", True),
            }[stage]
    classes = [state]
    if nature == "TEMPORARY" and visible:
        classes.append("TEMPORARY")
    if any(activity.get("critical") is True for activity in activities):
        classes.append("CRITICAL")
    if threshold and any(near_critical(activity, threshold) is True for activity in activities):
        classes.append("NEAR_CRITICAL")
    if blocked:
        classes.append("BLOCKED_BY_READINESS")
    # Imported status is evaluated only at the explicitly selected Data Date.
    # Future playback does not invent an actual delay or physical completion.
    if not baseline and data_date and selected == instant(data_date, timezone_name):
        for activity in activities:
            status = str(activity.get("status", "")).replace(" ", "_").upper()
            try:
                planned_finish = instant(activity.get("planned_finish"), timezone_name)
            except (ValueError, TypeError):
                planned_finish = None
            if (
                status in {"NOT_STARTED", "IN_PROGRESS"}
                and not activity.get("actual_finish")
                and planned_finish
                and planned_finish < selected
            ):
                classes.append("DELAYED")
    return {
        "state": state,
        "semantic_state": semantic,
        "visible": visible,
        "visual_classes": list(dict.fromkeys(classes)),
        "mapping_issues": list(dict.fromkeys(issues)),
        "state_basis": "SCHEDULE_DATE_PROJECTION_NOT_PHYSICAL_CERTIFICATION",
    }


def compare_states(baseline, current):
    """Same-date semantic variance. Never derive forecast dates or float."""
    if baseline is None:
        return "ADDED_TO_CURRENT"
    if current is None:
        return "ABSENT_FROM_CURRENT"
    if baseline["state"] == "UNKNOWN" or current["state"] == "UNKNOWN":
        return "UNRESOLVED"
    if baseline["semantic_state"] == current["semantic_state"]:
        return "ALIGNED"
    stages = {"NOT_STARTED": 0, "IN_PROGRESS": 1, "TEMPORARY": 2, "MAINTENANCE": 1, "COMPLETED": 3, "REMOVED": 3}
    before, after = stages.get(baseline["state"]), stages.get(current["state"])
    if before is not None and after is not None and after < before:
        return "BEHIND_BASELINE"
    if before is not None and after is not None and after > before:
        return "AHEAD_OF_BASELINE"
    return "STATE_DIFFERS"
