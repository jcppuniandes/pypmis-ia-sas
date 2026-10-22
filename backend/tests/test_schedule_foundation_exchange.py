"""Pure real-file parser/exchange checks. These do not certify a Primavera application import."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.modules.schedule_foundation import exchange
from app.modules.schedule_foundation.exchange import (
    ScheduleParseError,
    diff_schedule,
    export_schedule_xml,
    parse_schedule_source,
    validate_snapshot,
)
from app.services.schedule_parser import parse_xer as legacy_parse_xer

FIXTURES = Path(__file__).parent / "fixtures"


def source(suffix="xml"):
    return (FIXTURES / f"schedule-foundation-p6.{suffix}").read_bytes()


def snapshot():
    return parse_schedule_source(source(), "source.xml")["snapshot"]


@pytest.mark.parametrize("suffix", ["xml", "xer"])
def test_real_schedule_source_data_date_wbs_activities_calendars_and_hash(suffix):
    raw = source(suffix)
    original = bytes(raw)
    result = parse_schedule_source(raw, f"fixture.{suffix}")
    assert result["validation"]["can_accept"], result["validation"]
    assert result["source_hash"] == sha256(raw).hexdigest() and raw == original
    data = result["snapshot"]
    assert data["project"]["data_date"] == "2026-10-20T08:00:00"
    assert [row["path"] for row in data["wbs"]] == ["ROOT", "ROOT/FIELD"]
    assert [row["hours_per_day"] for row in data["calendars"]] == [10, 6]
    assert data["activities"][0]["original_duration"] == 20
    assert data["activities"][0]["duration_unit"] == "HOUR"
    assert data["activities"][1]["remaining_duration"] == 6
    assert data["activities"][2]["activity_type"] == "Finish Milestone"
    assert len(data["codes"]) == 2 and len(data["code_assignments"]) == 1
    assert not result["supported_subset"]["cpm_calculated"]


@pytest.mark.parametrize("suffix", ["xml", "xer"])
def test_four_relationship_types_signed_lags_and_external_identity_preserved(suffix):
    data = parse_schedule_source(source(suffix), f"file.{suffix}")["snapshot"]
    assert [row["relationship_type"] for row in data["relationships"][:4]] == ["FS", "SS", "FF", "SF"]
    assert [row["lag"] for row in data["relationships"][:4]] == [2, -1, 0, 0]
    assert all(row["lag_unit"] == "HOUR" for row in data["relationships"])
    external = data["external_links"][0]
    assert external["predecessor_external_id"] == "9001" and external["predecessor_project_external_id"] == "2"
    assert external["resolution"] == "EXTERNAL_PROJECT"
    assert "9001" not in {row["external_id"] for row in data["activities"]}


def test_source_float_criticality_and_percent_complete_unknown_are_not_inferred():
    data = snapshot()
    assert data["activities"][0]["total_float"] == 10 and data["activities"][0]["critical"] is False
    assert data["activities"][1]["total_float"] == -2 and data["activities"][1]["critical"] is True
    assert data["activities"][2]["total_float"] is None and data["activities"][2]["critical"] is None
    assert data["activities"][1]["percent_complete"] == 50
    assert all(not row["progress_authority"] and row["cpm_source"] == "P6_IMPORTED" for row in data["activities"])


def test_native_xer_float_does_not_invent_criticality_or_map_longest_path_to_critical():
    result = parse_schedule_source(source("xer"), "native.xer")
    assert result["snapshot"]["activities"][1]["total_float"] == -2
    assert all(row["critical"] is None for row in result["snapshot"]["activities"])
    assert "IMPORTED_CRITICALITY_UNKNOWN" in result["validation"]["warnings"]


def test_xml_calendar_workweek_shifts_and_exception_structure_retained():
    calendar = snapshot()["calendars"][0]
    assert calendar["workweek"]["StandardWorkHours"]["WorkTime"] == {"Start": "07:00:00", "Finish": "17:00:00"}
    assert calendar["exceptions"]["HolidayOrException"]["Date"] == "2026-12-25T00:00:00"
    data = snapshot()
    data["calendars"][0]["hours_per_day"] = None
    data["calendars"][0]["source_fields"].pop("HoursPerDay")
    assert "CALENDAR_HOURS_PER_DAY_UNKNOWN_NO_CONVERSION" in validate_snapshot(data)["warnings"]
    assert data["activities"][0]["original_duration"] == 20


def test_xml_constraints_primary_and_secondary_preserve_types_and_dates():
    raw = source().replace(
        b"</Activity>",
        b"<SecondaryConstraintType>Finish On or Before</SecondaryConstraintType><SecondaryConstraintDate>2026-12-01T17:00:00</SecondaryConstraintDate></Activity>",
        1,
    )
    data = parse_schedule_source(raw, "constraints.xml")["snapshot"]
    assert [row["type"] for row in data["constraints"]] == [
        "Start On or After",
        "Finish On or Before",
        "Mandatory Finish",
    ]
    assert data["constraints"][1]["slot"] == 2


def test_xml_export_is_actual_xml_parser_loop_with_core_semantics_and_no_native_baseline_claim():
    original = snapshot()
    raw = export_schedule_xml(original, baseline_reference={"baseline_id": 42, "hash": "governed"})
    assert ET.fromstring(raw).tag.endswith("}APIBusinessObjects")
    actual = parse_schedule_source(raw, "export.xml")
    assert actual["validation"]["can_accept"]
    for collection in ("wbs", "activities", "calendars", "relationships", "constraints", "codes", "code_assignments"):
        assert len(actual["snapshot"][collection]) == len(original[collection])
    for before, after in zip(original["activities"], actual["snapshot"]["activities"], strict=True):
        assert {key: before[key] for key in before if key != "source_fields"} == {
            key: after[key] for key in after if key != "source_fields"
        }
    assert actual["snapshot"]["calendars"][0]["exceptions"] == original["calendars"][0]["exceptions"]
    assert b"BaselineProject" not in raw
    assert not actual["supported_subset"]["native_baseline_transport_supported"]
    assert not actual["supported_subset"]["p6_application_roundtrip_verified"]


def test_native_xer_opaque_calendar_blocks_claimed_lossless_xml_export():
    data = parse_schedule_source(source("xer"), "input.xer")["snapshot"]
    assert data["calendars"][0]["opaque_calendar_data"]
    with pytest.raises(ScheduleParseError, match="OPAQUE_CALENDAR"):
        export_schedule_xml(data)


@pytest.mark.parametrize(
    "change,error",
    [
        ("NaN", "SOURCE_NUMBER_INVALID"),
        ("Infinity", "SOURCE_NUMBER_INVALID"),
        ("PT2H", "SOURCE_NUMBER_INVALID"),
        ("-1", "DURATION_NEGATIVE"),
    ],
)
def test_invalid_source_numbers_or_units_are_not_coerced_into_valid_quantity(change, error):
    raw = source().replace(
        b"<PlannedDuration>20</PlannedDuration>", f"<PlannedDuration>{change}</PlannedDuration>".encode(), 1
    )
    result = parse_schedule_source(raw, "bad.xml")
    assert not result["validation"]["can_accept"] and error in result["validation"]["errors"]


@pytest.mark.parametrize(
    "kind,mutate,error",
    [
        (
            "duplicate",
            lambda data: data["activities"].append(deepcopy(data["activities"][0])),
            "ACTIVITIES_DUPLICATE_ID",
        ),
        ("missing_date", lambda data: data["project"].update(data_date=None), "DATA_DATE_REQUIRED"),
        ("invalid_date", lambda data: data["project"].update(data_date="yesterday"), "DATA_DATE_INVALID"),
        ("wbs_cycle", lambda data: data["wbs"][0].update(parent_external_id="101"), "WBS_HIERARCHY_CYCLE"),
        ("dangling_wbs", lambda data: data["activities"][0].update(wbs_external_id="alien"), "ACTIVITY_WBS_UNRESOLVED"),
        (
            "unknown_relation",
            lambda data: data["relationships"][0].update(relationship_type="UNKNOWN"),
            "RELATIONSHIP_TYPE_UNSUPPORTED",
        ),
        (
            "invalid_activity_date",
            lambda data: data["activities"][0].update(actual_start="never"),
            "ACTIVITY_DATE_INVALID",
        ),
        (
            "invalid_percent",
            lambda data: data["activities"][0].update(percent_complete=101),
            "IMPORTED_PERCENT_COMPLETE_OUT_OF_RANGE",
        ),
        (
            "dangling_code",
            lambda data: data["code_assignments"][0].update(value_external_id="alien"),
            "ACTIVITY_CODE_ASSIGNMENT_UNRESOLVED",
        ),
    ],
)
def test_structural_and_source_validation_failure_cases(kind, mutate, error):
    data = snapshot()
    mutate(data)
    assert error in validate_snapshot(data)["errors"], kind


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"garbage",
        b"<bad",
        b"<Project/>",
        b"<!DOCTYPE x [<!ENTITY y 'bad'>]><APIBusinessObjects>&y;</APIBusinessObjects>",
    ],
)
def test_invalid_xml_container_and_entity_source_rejected(payload):
    with pytest.raises(ScheduleParseError):
        parse_schedule_source(payload, "bad.xml")


def test_utf16_dtd_cannot_bypass_utf8_entity_guard():
    payload = '<!DOCTYPE x [<!ENTITY y "bad">]><APIBusinessObjects>&y;</APIBusinessObjects>'.encode("utf-16")
    with pytest.raises(ScheduleParseError, match="UTF8"):
        parse_schedule_source(payload, "bad.xml")


@pytest.mark.parametrize(
    "payload",
    [
        b"ERMHDR\t19\n%E\n",
        b"ERMHDR\t19\n%T\tTASK\n%F\ta\ta\n%E",
        b"ERMHDR\t19\n%T\tTASK\n%F\ta\n%R\t1\t2\n%E",
        b"ERMHDR\t19\n%T\tTASK\n%F\ta\n%R\t1\n",
        b"ERMHDR\t19\n%E\n%T\tTASK",
    ],
)
def test_native_xer_structural_errors_rejected(payload):
    with pytest.raises(ScheduleParseError):
        parse_schedule_source(payload, "bad.xer")


def test_native_xer_parser_characterization_distinguishes_legacy_marker_subset():
    with pytest.raises(ScheduleParseError, match="task table"):
        legacy_parse_xer(source("xer").decode())
    actual = parse_schedule_source(source("xer"), "native.xer")
    assert actual["validation"]["can_accept"]


def test_legacy_xer_adapter_reuses_existing_tokenizer_without_implicit_acceptance():
    raw = b"%FMT:19\n%ER project\nproj_id\tproj_short_name\tlast_recalc_date\n1\tLEGACY\t2026-10-20\n%TR project\n%ER task\ntask_id\ttask_code\ttask_name\n100\tA100\tLegacy\n%TR task\n%E\n"
    result = parse_schedule_source(raw, "legacy.xer")
    assert result["snapshot"]["activities"][0]["code"] == "A100"
    assert not result["validation"]["can_accept"] and "ACTIVITY_WBS_UNRESOLVED" in result["validation"]["errors"]


def test_unsupported_fields_and_objects_reported_while_original_hash_preserved():
    raw = (
        source()
        .replace(b"<PlannedDuration>20", b"<CustomUnknown>retained</CustomUnknown><PlannedDuration>20", 1)
        .replace(b"</APIBusinessObjects>", b"<Resource><ObjectId>900</ObjectId></Resource></APIBusinessObjects>")
    )
    result = parse_schedule_source(raw, "extension.xml")
    assert "Resource" in result["unsupported_fields"] and "activities.CustomUnknown" in result["unsupported_fields"]
    assert result["snapshot"]["activities"][0]["source_fields"]["CustomUnknown"] == "retained"
    assert result["source_hash"] == sha256(raw).hexdigest()


def test_identity_based_diff_preserves_mapping_impacts_and_source_immutability():
    before = snapshot()
    frozen = deepcopy(before)
    after = deepcopy(before)
    after["wbs"][1]["parent_external_id"] = ""
    after["wbs"][1]["name"] = "Moved and renamed"
    after["activities"].pop()
    after["activities"][0]["remaining_duration"] = 5
    after["activities"][0]["wbs_external_id"] = "100"
    after["project"]["data_date"] = "2026-10-27T08:00:00"
    result = diff_schedule(before, after)
    assert result["activities"]["removed"] == ["1004"]
    assert result["mapping_impacts"]["activities"]["removed"] == ["1004"]
    assert result["mapping_impacts"]["wbs"]["changed"] == ["101"]
    assert "remaining_duration" in result["activities"]["changed"][0]["fields"]
    assert result["data_date"]["changed"] and before == frozen


@pytest.mark.parametrize(
    "payload",
    [None, [], {"project": []}, {"project": {}, "activities": "wrong"}, {"project": {}, "constraints": ["wrong"]}],
)
def test_malformed_manual_snapshot_reports_errors_instead_of_crashing(payload):
    assert not validate_snapshot(payload)["can_accept"]


@pytest.mark.parametrize(
    "collection,field,value",
    [
        ("activities", "code", ["not", "a", "code"]),
        ("activities", "external_id", {"id": "1001"}),
        ("wbs", "parent_external_id", ["100"]),
        ("calendars", "external_id", ["10"]),
        ("calendars", "type", {"name": "Project"}),
        ("relationships", "relationship_type", ["FS"]),
        ("constraints", "activity_external_id", ["1001"]),
        ("codes", "kind", ["TYPE"]),
        ("codes", "external_id", {"not": "an id"}),
        ("code_assignments", "value_external_id", ["3002"]),
        ("activities", "source_fields", None),
        ("activities", "source_fields", []),
        ("calendars", "source_fields", "not a dictionary"),
    ],
)
def test_untrusted_draft_identity_labels_and_metadata_return_validation_not_500(collection, field, value):
    data = snapshot()
    data[collection][0][field] = value
    result = validate_snapshot(data)
    assert result["errors"] and not result["can_accept"]
    with pytest.raises(ScheduleParseError, match="INVALID_SNAPSHOT"):
        export_schedule_xml(data)


@pytest.mark.parametrize("value", ["8", "bad", [], {}, True])
def test_untrusted_calendar_hours_cannot_raise_type_error(value):
    data = snapshot()
    data["calendars"][0]["hours_per_day"] = value
    result = validate_snapshot(data)
    if value == "8":
        assert result["can_accept"]
    else:
        assert "CALENDAR_HOURS_PER_DAY_INVALID" in result["errors"] and not result["can_accept"]


def test_null_activity_type_is_invalid_before_health_milestone_classification():
    data = snapshot()
    data["activities"][0]["activity_type"] = None
    result = validate_snapshot(data)
    assert "ACTIVITY_TYPE_REQUIRED" in result["errors"] and not result["can_accept"]


@pytest.mark.parametrize("value", [True, False])
def test_boolean_relationship_lag_is_not_a_numeric_source_duration(value):
    data = snapshot()
    data["relationships"][0]["lag"] = value
    result = validate_snapshot(data)
    assert "RELATIONSHIP_LAG_INVALID" in result["errors"] and not result["can_accept"]


@pytest.mark.parametrize(
    "field", ["original_duration", "remaining_duration", "total_float", "free_float", "percent_complete"]
)
@pytest.mark.parametrize("value", [True, False])
def test_boolean_activity_numbers_are_rejected_without_coercion(field, value):
    data = snapshot()
    data["activities"][0][field] = value
    result = validate_snapshot(data)
    assert "ACTIVITY_NUMBER_INVALID" in result["errors"] and not result["can_accept"]


def test_input_record_and_size_limits(monkeypatch):
    monkeypatch.setattr(exchange, "MAX_SOURCE_BYTES", 2)
    with pytest.raises(ScheduleParseError, match="SIZE_LIMIT"):
        parse_schedule_source(source(), "large.xml")


def test_export_non_native_object_ids_and_day_conversion_are_explicitly_blocked():
    data = snapshot()
    data["activities"][0]["duration_unit"] = "DAY"
    with pytest.raises(ScheduleParseError, match="HOUR_UNITS_REQUIRED"):
        export_schedule_xml(data)
    data = snapshot()
    data["wbs"][0]["external_id"] = "non-numeric"
    data["wbs"][1]["parent_external_id"] = "non-numeric"
    data["activities"][2]["wbs_external_id"] = "non-numeric"
    data["activities"][3]["wbs_external_id"] = "non-numeric"
    with pytest.raises(ScheduleParseError, match="INTEGER_OBJECT_IDS"):
        export_schedule_xml(data)


def test_xml_duplicate_scalar_and_empty_business_object_rejected():
    duplicate = source().replace(b"<ObjectId>1</ObjectId>", b"<ObjectId>1</ObjectId><ObjectId>2</ObjectId>", 1)
    with pytest.raises(ScheduleParseError, match="DUPLICATE_SCALAR"):
        parse_schedule_source(duplicate, "duplicate.xml")
    empty = source().replace(b"<WBS>", b"<WBS/>", 1).replace(b"</WBS>", b"", 1)
    with pytest.raises(ScheduleParseError):
        parse_schedule_source(empty, "empty.xml")


def test_deep_hierarchy_is_bounded_for_import_and_manual_snapshots(monkeypatch):
    data = snapshot()
    monkeypatch.setattr(exchange, "MAX_XML_DEPTH", 3)
    data["wbs"] = [
        {"external_id": str(i), "parent_external_id": str(i - 1) if i > 1 else "", "code": str(i)} for i in range(1, 6)
    ]
    assert "WBS_HIERARCHY_DEPTH_LIMIT" in validate_snapshot(data)["errors"]


def test_xer_table_and_field_counts_are_bounded(monkeypatch):
    monkeypatch.setattr(exchange, "MAX_XER_TABLES", 1)
    with pytest.raises(ScheduleParseError, match="TABLE_LIMIT"):
        parse_schedule_source(source("xer"), "many.xer")


def test_export_generation_is_deterministic_and_does_not_mutate_snapshot():
    data = snapshot()
    before = deepcopy(data)
    assert export_schedule_xml(data) == export_schedule_xml(data)
    assert data == before
