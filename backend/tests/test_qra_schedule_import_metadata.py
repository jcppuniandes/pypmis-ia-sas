"""Canonical manual import retains source declarations, without CPM or QRA."""

import hashlib

from app.domain.models import ScheduleImport, ScheduleSource
from app.services.schedule_ingestion import ScheduleIngestionService


def service():
    return ScheduleIngestionService(None)


def xml_activity(extra=""):
    return f"""<Project xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
      <DataDate>2026-10-09T08:00:00</DataDate>
      <Calendar><ObjectId>7</ObjectId><Name>Declared 5 day</Name><Type>Project</Type></Calendar>
      <WBS><ObjectId>10</ObjectId><Code>PLANT</Code><Name>Plant</Name></WBS>
      <Activity><ObjectId>100</ObjectId><Id>A100</Id><Name>Design</Name><WBSObjectId>10</WBSObjectId>
      <PlannedStartDate>2026-10-09T08:00:00</PlannedStartDate>
      <PlannedFinishDate>2026-10-14T17:00:00</PlannedFinishDate>{extra}</Activity>
    </Project>""".encode()


def test_xml_metadata_keeps_calendar_constraints_status_and_raw_durations():
    content = xml_activity("""<CalendarObjectId>7</CalendarObjectId><PlannedDuration>40</PlannedDuration>
      <RemainingDuration>24</RemainingDuration><DurationUnit>HOURS</DurationUnit>
      <Type>Task Dependent</Type><Status>In Progress</Status>
      <PrimaryConstraintType>Start On</PrimaryConstraintType><PrimaryConstraintDate>2026-10-09</PrimaryConstraintDate>
      <ActualStartDate>2026-10-09T08:00:00</ActualStartDate>""")
    parsed = service().parse("manual-p6.xml", content)
    metadata = parsed.source_metadata
    assert metadata["source_file_hash"] == hashlib.sha256(content).hexdigest()
    assert metadata["imported_source"] == "p6_xml"
    assert metadata["schema_version"] == 1
    row = metadata["activities"][0]
    assert row["external_id"] == "A100"
    assert row["calendar_ref"] == "7"
    assert row["original_duration"] == "40"
    assert row["remaining_duration"] == "24"
    assert row["duration_unit"] == "HOURS"
    assert row["status"] == "In Progress"
    assert row["primary_constraint_type"] == "Start On"
    assert row["actual_start"] == "2026-10-09T08:00:00"
    assert row["milestone"] is False
    assert metadata["calendars"][0]["source_id"] == "7"
    assert "Declared 5 day" in metadata["calendars"][0]["source_data"]
    assert not any(key in metadata for key in ("cpm", "simulation", "contingency"))


def test_xml_missing_units_and_attributes_remain_unknown_not_date_derived():
    parsed = service().parse("manual-p6.xml", xml_activity("<PlannedDuration>40</PlannedDuration>"))
    row = parsed.source_metadata["activities"][0]
    assert row["original_duration"] == "40"
    for key in ("remaining_duration", "duration_unit", "status", "calendar_ref", "milestone"):
        assert row[key] is None
    assert row["primary_constraint_type"] is None


def test_xml_each_activity_keeps_its_own_declared_metadata():
    content = xml_activity(
        "<CalendarObjectId>7</CalendarObjectId><PlannedDuration>40</PlannedDuration>"
        "<RemainingDuration>24</RemainingDuration><DurationUnit>HOURS</DurationUnit>"
        "<Status>In Progress</Status><Type>Task Dependent</Type>"
    ).replace(
        b"</Project>",
        b"<Activity><ObjectId>200</ObjectId><Id>A200</Id><Name>Finish</Name>"
        b"<CalendarObjectId>9</CalendarObjectId><PlannedDuration>0</PlannedDuration>"
        b"<RemainingDuration>0</RemainingDuration><DurationUnit>DAYS</DurationUnit>"
        b"<Status>Not Started</Status><Type>Finish Milestone</Type></Activity></Project>",
    )
    rows = service().parse("two-activities.xml", content).source_metadata["activities"]
    assert [
        (row["external_id"], row["calendar_ref"], row["original_duration"], row["duration_unit"]) for row in rows
    ] == [("A100", "7", "40", "HOURS"), ("A200", "9", "0", "DAYS")]
    assert [row["status"] for row in rows] == ["In Progress", "Not Started"]
    assert [row["milestone"] for row in rows] == [False, True]


def test_xml_zero_negative_and_invalid_declared_duration_not_repaired():
    for duration in ("0", "-5", "INVALID"):
        metadata = service().parse("manual-p6.xml", xml_activity(f"<PlannedDuration>{duration}</PlannedDuration>"))
        assert metadata.source_metadata["activities"][0]["original_duration"] == duration


def test_xml_milestone_is_explicit_type_not_inferred_from_equal_dates():
    row = service().parse("manual-p6.xml", xml_activity("<Type>Finish Milestone</Type>"))
    assert row.source_metadata["activities"][0]["milestone"] is True


def test_xml_secondary_constraint_and_source_hash_detect_changes():
    before = xml_activity("<SecondaryConstraintType>Finish On</SecondaryConstraintType>")
    after = xml_activity("<SecondaryConstraintType>Finish On or Before</SecondaryConstraintType>")
    first = service().parse("source.xml", before).source_metadata
    second = service().parse("source.xml", after).source_metadata
    assert first["source_file_hash"] != second["source_file_hash"]
    assert second["activities"][0]["secondary_constraint_type"] == "Finish On or Before"


def test_xer_metadata_preserves_declared_hour_fields_and_calendar():
    content = b"""%T\tPROJECT
%F\tproj_id\tlast_recalc_date
%R\t1\t2026-10-09 08:00
%T\tCALENDAR
%F\tclndr_id\tclndr_name\tclndr_type\tclndr_data
%R\t7\tImported calendar\tCA_Project\tRAW_WORK_WEEK
%T\tTASK
%F\ttask_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\tclndr_id\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\tstatus_code\ttask_type\tcstr_type
%R\t100\tA100\tDesign\t2026-10-09\t2026-10-14\t7\t40\t0\tTK_Complete\tTT_Task\tCS_SO
"""
    metadata = service().parse("manual.xer", content).source_metadata
    assert metadata["imported_source"] == "p6_xer"
    row = metadata["activities"][0]
    assert row["external_id"] == "A100"
    assert row["original_duration"] == "40"
    assert row["remaining_duration"] == "0"
    assert row["duration_unit"] == "HOURS"
    assert row["status"] == "TK_Complete"
    assert row["primary_constraint_type"] == "CS_SO"
    assert metadata["calendars"][0]["source_data"] == "RAW_WORK_WEEK"


def test_malformed_xml_is_honestly_empty_metadata():
    content = b"<Project><Activity>"
    parsed = service().parse("invalid.xml", content)
    assert parsed.source_metadata["activities"] == []
    assert parsed.source_metadata["calendars"] == []
    assert parsed.source_metadata["source_file_hash"] == hashlib.sha256(content).hexdigest()
    assert any(finding.check_code == "NO_ACTIVITIES" for finding in parsed.findings)


def test_legacy_schedule_import_has_no_fabricated_metadata():
    row = ScheduleImport(tenant_id=1, project_id=1, source=ScheduleSource.p6_xml, file_name="old.xml")
    assert row.source_metadata == {}


def test_p6_project_deadline_is_not_a_data_date():
    content = xml_activity().replace(
        b"<DataDate>2026-10-09T08:00:00</DataDate>", b"<MustFinishByDate>2026-12-31</MustFinishByDate>"
    )
    assert service().parse("source.xml", content).data_date is None


def test_invalid_raw_relationship_type_is_not_silently_repaired_in_metadata():
    content = xml_activity().replace(
        b"</Project>",
        b"""<Relationship>
      <PredecessorActivityObjectId>100</PredecessorActivityObjectId>
      <SuccessorActivityId>A999</SuccessorActivityId><Type>UNKNOWN_LOGIC</Type>
      <Lag>-16</Lag><LagUnit>HOURS</LagUnit></Relationship></Project>""",
    )
    relationship = service().parse("source.xml", content).source_metadata["relationships"][0]
    assert relationship["predecessor"] == "A100"
    assert relationship["successor"] == "A999"
    assert relationship["relationship_type"] == "UNKNOWN_LOGIC"
    assert relationship["lag"] == "-16"
