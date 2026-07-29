from app.domain.models import ScheduleSource
from app.services.schedule_ingestion import ScheduleIngestionService


def _service() -> ScheduleIngestionService:
    return ScheduleIngestionService(None)  # type: ignore[arg-type]


def test_xer_import_reads_costs_from_resource_assignments() -> None:
    content = b"""%T\tPROJECT
%F\tproj_id\tlast_recalc_date\tcurrency_id
%R\t1\t2026-03-15 08:00\tCOP
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
    assert parsed.detected_currency == "COP"
    assert parsed.currency_confidence == "detected"
    assert parsed.currency_source == "PROJECT.currency_id"
    assert parsed.total_imported_cost == 1250.50
    assert parsed.cost_loaded_activity_count == 1
    assert parsed.cost_loaded_activity_percent == 100
    assert parsed.cost_source_summary["TASKRSRC.target_cost"] == 1
    assert "1 cost-loaded activities" in parsed.validation_summary
    assert not any(finding.check_code == "NO_COST_LOADING" for finding in parsed.findings)


def test_xer_import_reads_costs_from_project_cost_expenses() -> None:
    content = b"""%T\tPROJECT
%F\tproj_id\tlast_recalc_date\tcurrency_id
%R\t1\t2026-05-07 00:00\tUSD
%T\tPROJWBS
%F\twbs_id\twbs_short_name\twbs_name
%R\t10\tENG\tEngineering
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t10\tA1000\tEngineering deliverable\t2026-05-07 07:00\t2026-05-10 17:00\t0
%R\t101\t10\tA1010\tProcurement package\t2026-05-11 07:00\t2026-05-14 17:00\t0
%T\tPROJCOST
%F\tcost_item_id\tproj_id\ttask_id\tcost_name\tact_cost\tcost_per_qty\tremain_cost\ttarget_cost\tcost_load_type\ttarget_qty
%R\t9001\t1\t100\tPresupuesto EXP\t0.0000\t500000.0000\t500000.0000\t500000.0000\tCL_Uniform\t1
%R\t9002\t1\t101\tPresupuesto EXP\t0.0000\t300000.0000\t300000.0000\t300000.0000\tCL_Uniform\t1
"""

    parsed = _service().parse("baseline.xer", content)

    assert parsed.activities[0].planned_cost == 500000
    assert parsed.activities[1].planned_cost == 300000
    assert parsed.total_imported_cost == 800000
    assert parsed.cost_loaded_activity_count == 2
    assert parsed.cost_loaded_activity_percent == 100
    assert parsed.cost_source_summary["PROJCOST.target_cost"] == 2
    assert "2 cost-loaded activities" in parsed.validation_summary
    assert not any(finding.check_code == "NO_COST_LOADING" for finding in parsed.findings)


def test_xer_import_maps_project_wbs_hierarchy_from_projwbs_fields() -> None:
    content = b"""%T\tPROJECT
%F\tproj_id\tproj_short_name\tlast_recalc_date\tcurrency_id
%R\t1\tP&Pmis-PY-1\t2026-05-07 00:00\tUSD
%T\tPROJWBS
%F\twbs_id\tproj_id\tseq_num\tproj_node_flag\tparent_wbs_id\twbs_short_name\twbs_name
%R\t1\t1\t500\tY\t999\tP&Pmis-PY-1\tProyecto Piloto
%R\t10\t1\t10\tN\t1\t1\tIngenieria
%R\t20\t1\t20\tN\t1\t2\tProcura
%R\t40\t1\t40\tN\t1\t4\tConstruccion
%R\t41\t1\t41\tN\t40\t1\tEstructura Concreto
%R\t42\t1\t42\tN\t40\t2\tInstalaciones Mecanicas, Electricas, Hidraulicas
%T\tTASK
%F\ttask_id\twbs_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt
%R\t100\t41\tA1000\tNew Activity\t2026-05-15 07:00\t2026-07-03 17:00\t0
"""

    parsed = _service().parse("baseline.xer", content)

    assert parsed.activities[0].wbs_code == "P&Pmis-PY-1-4-1"
    assert parsed.activities[0].wbs_name == "Estructura Concreto"
    wbs_by_code = {node.code: node for node in parsed.wbs_nodes}
    assert wbs_by_code["P&Pmis-PY-1"].name == "Proyecto Piloto"
    assert wbs_by_code["P&Pmis-PY-1-4"].parent_source_id == wbs_by_code["P&Pmis-PY-1"].source_id
    assert wbs_by_code["P&Pmis-PY-1-4-1"].parent_source_id == wbs_by_code["P&Pmis-PY-1-4"].source_id
    assert wbs_by_code["P&Pmis-PY-1-4-1"].level == 3


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
    assert parsed.total_imported_cost == 2500
    assert parsed.cost_loaded_activity_count == 1
    assert parsed.cost_loaded_activity_percent == 100
    assert parsed.cost_source_summary["ResourceAssignment.PlannedCost"] == 1
    assert "1 cost-loaded activities" in parsed.validation_summary
    assert not any(finding.check_code == "NO_COST_LOADING" for finding in parsed.findings)


def test_malformed_xml_is_rejected_as_schedule_quality_issue() -> None:
    parsed = _service().parse("bad.xml", b"<Project><Activity>")

    assert parsed.activities == []
    assert parsed.quality_score == 0
    assert parsed.findings[0].check_code == "NO_ACTIVITIES"
