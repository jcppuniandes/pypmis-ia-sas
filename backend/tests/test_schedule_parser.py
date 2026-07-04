import pytest

from app.services.schedule_parser import (
    DCMAValidationResult,
    ScheduleParseError,
    parse_p6_xml,
    parse_xer,
)

MINIMAL_XER = """%FMT:19
%ER  project
proj_id\tproj_short_name\tplan_start_date
1\tTEST_PROJECT\t2024-01-01 00:00
%TR  project
%ER  task
task_id\tproj_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\tphys_complete_pct
1001\t1\tA1000\tMobilization\t2024-01-01 00:00\t2024-01-15 00:00\t0
1002\t1\tA1010\tSite Prep\t2024-01-15 00:00\t2024-02-01 00:00\t0
%TR  task
%E
"""


def test_parse_xer_returns_activities() -> None:
    result = parse_xer(MINIMAL_XER)
    assert len(result.activities) == 2
    assert result.activities[0]["task_code"] == "A1000"
    assert result.activities[1]["task_code"] == "A1010"


def test_parse_xer_returns_project_meta() -> None:
    result = parse_xer(MINIMAL_XER)
    assert result.project_meta["proj_short_name"] == "TEST_PROJECT"


def test_parse_xer_missing_task_table_raises() -> None:
    with pytest.raises(ScheduleParseError, match="task table"):
        parse_xer("%FMT:19\n%E\n")


def test_dcma_flags_missing_logic() -> None:
    result = parse_xer(MINIMAL_XER)
    report = result.dcma_validate()
    assert isinstance(report, DCMAValidationResult)
    assert report.total_activities == 2
    assert report.missing_logic_count == 2
    assert report.missing_logic_pct == pytest.approx(100.0)
    assert report.passed is False


def test_dcma_passes_with_full_logic() -> None:
    xer_with_rel = MINIMAL_XER.replace(
        "%E\n",
        "%ER  taskpred\npred_task_id\ttask_id\tpred_type\tlag_hr_cnt\n1001\t1002\tFS\t0\n%TR  taskpred\n%E\n",
    )
    result = parse_xer(xer_with_rel)
    report = result.dcma_validate()
    assert report.missing_logic_count == 0
    assert report.passed is True


def test_parse_p6_xml_returns_activities() -> None:
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
  <Activity>
    <Id>A1000</Id>
    <Name>Mobilization</Name>
    <PlannedStartDate>2024-01-01T00:00:00</PlannedStartDate>
    <PlannedFinishDate>2024-01-15T00:00:00</PlannedFinishDate>
  </Activity>
</APIBusinessObjects>
"""
    result = parse_p6_xml(xml_content)
    assert len(result.activities) == 1
    assert result.activities[0]["task_code"] == "A1000"


def test_parse_p6_xml_invalid_raises() -> None:
    with pytest.raises(ScheduleParseError, match="Invalid XML"):
        parse_p6_xml("not actually xml <<")
