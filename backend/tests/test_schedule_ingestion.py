from app.domain.models import ScheduleSource
from app.services.schedule_ingestion import ScheduleIngestionService


def _service() -> ScheduleIngestionService:
    return ScheduleIngestionService(None)  # type: ignore[arg-type]


def test_xer_import_reads_costs_from_resource_assignments() -> None:
    content = b"""%T\tPROJECT
%F\tproj_id\tlast_recalc_date
%R\t1\t2026-03-15 08:00
%T\tPROJWBS
%F\twbs_id\twbs_short_name\twbs_name
%R\t10\tPIPE\tPipe Rack
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t10\tA100\tInstall pipe rack\t2026-03-01 08:00\t2026-03-20 17:00\t16
%T\tTASKRSRC
%F\ttask_id\ttarget_cost
%R\t100\t1250.50
"""

    parsed = _service().parse("baseline.xer", content)

    assert parsed.source == ScheduleSource.p6_xer
    assert parsed.data_date.isoformat() == "2026-03-15"
    assert parsed.activities[0].planned_cost == 1250.50
    assert "1 cost-loaded activities" in parsed.validation_summary
    assert not any(finding.check_code == "NO_COST_LOADING" for finding in parsed.findings)


def test_p6_xml_import_reads_costs_from_resource_assignments() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
  <WBS>
    <ObjectId>10</ObjectId>
    <Code>PIPE</Code>
    <Name>Pipe Rack</Name>
  </WBS>
  <Activity>
    <ObjectId>100</ObjectId>
    <Id>A100</Id>
    <Name>Install pipe rack</Name>
    <WBSObjectId>10</WBSObjectId>
    <PlannedStartDate>2026-03-01T08:00:00</PlannedStartDate>
    <PlannedFinishDate>2026-03-20T17:00:00</PlannedFinishDate>
    <TotalFloatDuration>PT16H</TotalFloatDuration>
  </Activity>
  <ResourceAssignment>
    <ActivityObjectId>100</ActivityObjectId>
    <PlannedCost>2500</PlannedCost>
  </ResourceAssignment>
</Project>
"""

    parsed = _service().parse("baseline.xml", content)

    assert parsed.source == ScheduleSource.p6_xml
    assert parsed.activities[0].external_id == "A100"
    assert parsed.activities[0].planned_cost == 2500
    assert "1 cost-loaded activities" in parsed.validation_summary
    assert not any(finding.check_code == "NO_COST_LOADING" for finding in parsed.findings)


def test_malformed_xml_is_rejected_as_schedule_quality_issue() -> None:
    parsed = _service().parse("bad.xml", b"<Project><Activity>")

    assert parsed.activities == []
    assert parsed.quality_score == 0
    assert parsed.findings[0].check_code == "NO_ACTIVITIES"
