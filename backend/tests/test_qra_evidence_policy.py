"""Contextual QRA policy/criteria unit contracts; never the operational DB."""

import json
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.modules.basic_data.service import BasicDataService
from app.modules.investment_evidence_policy.decision_criteria import criterion, evaluate_criteria
from app.modules.investment_evidence_policy.qra_evidence import (
    SCHEDULE_CAPABILITIES,
    apply_qra_context,
    qra_applicability,
    qra_criterion_issues,
    qra_criterion_value,
    qra_policy_issues,
    qra_result_issues,
    qra_summary,
)
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    PROVIDER_REGISTRY,
    InvestmentEvidencePolicyService,
    _hash,
    _requirement,
)
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.project_definition.schemas import InvestmentGateEvidenceOut
from app.modules.project_definition.service import ProjectDefinitionService
from app.modules.qra_foundation.service import QraFoundationService


def _qra_requirement(analysis="COST_QRA", *, classification="A", applicability="REQUIRED", **overrides):
    row = _requirement(
        "COST_QRA_RESULT" if analysis == "COST_QRA" else "SCHEDULE_QRA_RESULT",
        classification,
        scope="EACH_PROJECT",
        blocking=classification == "A",
        provider_key="QRA_RESULT_PROVIDER",
        coverage=100,
        rationale="Explicit contextual draft policy only",
        order=200,
    )
    row["qra_policy"] = {
        "analysis_type": analysis,
        "applicability": applicability,
        "governance_model_filter": ["CAPITAL_OWNER"],
        "project_type_filter": ["*"],
        "fel_stage_filter": ["*"],
        "project_risk_filter": ["*"],
        "project_complexity_filter": ["*"],
        "uncertainty_level_filter": ["*"],
        "analytical_readiness": "WARNINGS_ALLOWED",
        "convergence": "WARNING_ALLOWED",
        "scope_requirement": "WHOLE_PROJECT",
        "selected_percentiles": [50, 80, 90],
        "capability_requirements": deepcopy(SCHEDULE_CAPABILITIES) if analysis == "SCHEDULE_QRA" else {},
        "bc_consistency_required": False,
        **overrides,
    }
    return row


def _context(**overrides):
    return {
        "project_workspace_id": 14,
        "governance_model": "CAPITAL_OWNER",
        "project_type": "COMMERCIAL",
        "fel_stage": "FEL-3",
        "project_risk": "HIGH",
        "project_complexity": "HIGH",
        "uncertainty_level": "HIGH",
        "estimated_budget": "1000000",
        "currency_code": "USD",
        **overrides,
    }


def _value(analysis="COST_QRA", **overrides):
    return {
        "provider_key": "QRA_RESULT_PROVIDER",
        "analysis_type": analysis,
        "run_id": 1,
        "run_number": "QRR-000001",
        "model_definition_id": 1,
        "model_hash": "m" * 64,
        "run_hash": "r" * 64,
        "acceptance_hash": "a" * 64,
        "evidence_hash": "a" * 64,
        "source_current": True,
        "as_of": "2026-10-12T00:00:00",
        "analysis_scope": {"type": "ENTIRE_PROJECT", "refs": []},
        "readiness": "READY_WITH_WARNINGS",
        "convergence": {"status": "NOT_CONVERGED"},
        "selected_percentiles": [{"percentile": p, "value": p * 10} for p in (50, 80, 90)],
        "target_probabilities": {"probability_meeting_target_amount": 0.85},
        "result_semantics": {"currency": "USD", "target_amount": 1000},
        "warnings": ["NOT_CONVERGED"],
        "blockers": [],
        **overrides,
    }


@pytest.mark.parametrize("analysis", ["COST_QRA", "SCHEDULE_QRA"])
def test_one_provider_two_qualified_rows_and_no_default_requirement(analysis):
    assert qra_policy_issues(_qra_requirement(analysis)) == []
    assert PROVIDER_REGISTRY["QRA_RESULT_PROVIDER"]["status"] == "AVAILABLE"
    assert not any("_QRA_RESULT_PROVIDER" in key for key in PROVIDER_REGISTRY)
    assert all(
        "qra_policy" not in row
        for profile in DEFAULT_POLICY["gate_profiles"].values()
        for row in profile["requirements"]
    )


@pytest.mark.parametrize("governance", ["CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY_UNCLASSIFIED"])
def test_qra_not_forced_on_other_governance(governance):
    effective = apply_qra_context(_qra_requirement(), _context(governance_model=governance))
    assert effective["classification"] == "C" and not effective["required"]
    assert effective["qra_applicability"]["outcome"] == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    "key,context_field",
    [
        ("project_type_filter", "project_type"),
        ("fel_stage_filter", "fel_stage"),
        ("project_risk_filter", "project_risk"),
        ("uncertainty_level_filter", "uncertainty_level"),
        ("project_complexity_filter", "project_complexity"),
    ],
)
def test_contextual_dimensions_are_actual_governed_fields(key, context_field):
    row = _qra_requirement(**{key: ["OTHER"]})
    assert qra_applicability(row, _context())["outcome"] == "NOT_APPLICABLE"
    assert qra_applicability(row, _context(**{context_field: "UNSPECIFIED"}))["outcome"] == "NOT_EVALUABLE"


def test_value_band_no_fx_unknown_blocks_and_low_value_not_required():
    row = _qra_requirement(
        applicability="CONDITIONAL",
        value_band={"source": "PROJECT_CREATION_ESTIMATED_BUDGET", "currency": "USD", "minimum": 500000},
    )
    assert qra_applicability(row, _context())["outcome"] == "REQUIRED"
    assert qra_applicability(row, _context(estimated_budget=100))["outcome"] == "NOT_REQUIRED"
    unknown = apply_qra_context(row, _context(currency_code="COP"))
    assert unknown["qra_applicability"]["outcome"] == "NOT_EVALUABLE"
    assert unknown["required"] and unknown["blocking"] and unknown["classification"] == "A"


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"analysis_type": "INTEGRATED_COST_SCHEDULE_QRA"}, "QRA_ANALYSIS_TYPE_NOT_RELEASED_OR_MISMATCH"),
        ({"tail_convergence_required": True}, "QRA_TAIL_CONVERGENCE_NOT_RELEASED"),
        ({"selected_percentiles": [float("nan")]}, "INVALID_QRA_SELECTED_PERCENTILES"),
        ({"convergence": "ANY"}, "INVALID_QRA_CONVERGENCE_POLICY"),
        ({"freshness_days": 0}, "INVALID_QRA_FRESHNESS_DAYS"),
    ],
)
def test_invalid_qra_policy_rejected(changes, expected):
    assert expected in qra_policy_issues(_qra_requirement(**changes))


def test_mandatory_schedule_publish_range_must_declare_engine_bounds():
    assert "MANDATORY_SCHEDULE_QRA_SUPPORTED_CAPABILITY_RANGE_REQUIRED" in qra_policy_issues(
        _qra_requirement("SCHEDULE_QRA", capability_requirements={"schedule_state": "STARTED"})
    )
    assert qra_policy_issues(_qra_requirement("SCHEDULE_QRA")) == []


def test_validator_is_existing_policy_layer_and_no_class_a_manual_fallback():
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    policy = deepcopy(DEFAULT_POLICY)
    row = _qra_requirement()
    policy["gate_profiles"]["PYP-FFA"]["requirements"].append(row)
    service._validate_policy(policy)
    row["allow_manual_reference"] = True
    with pytest.raises(HTTPException) as error:
        service._validate_policy(policy)
    assert any("CLASS_A_NO_SILENT_FALLBACK" in issue for issue in error.value.detail["issues"])


def test_accepted_warning_not_converged_requires_explicit_policy():
    now = datetime(2026, 10, 12)
    assert qra_result_issues(_qra_requirement(), _value(), now=now) == []
    assert "QRA_CONVERGENCE_REQUIRED" in qra_result_issues(_qra_requirement(convergence="REQUIRED"), _value(), now=now)
    assert "QRA_ANALYTICAL_READINESS_NOT_MET" in qra_result_issues(
        _qra_requirement(analytical_readiness="READY_ONLY"), _value(), now=now
    )


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"analysis_type": "SCHEDULE_QRA"}, "QRA_ANALYSIS_TYPE_MISMATCH"),
        ({"analysis_scope": {"type": "SELECTED_WBS", "refs": ["A"]}}, "QRA_SCOPE_MISMATCH"),
        ({"selected_percentiles": []}, "QRA_CONFIGURED_PERCENTILE_NOT_IN_OUTPUT_CONTRACT"),
        ({"as_of": "2026-01-01"}, "QRA_EVIDENCE_EXPIRED"),
    ],
)
def test_result_qualifiers_and_freshness(changes, expected):
    assert expected in qra_result_issues(
        _qra_requirement(freshness_days=30), _value(**changes), now=datetime(2026, 10, 12)
    )


def test_schedule_work_calendar_cannot_satisfy_elapsed_requirement():
    row = _qra_requirement("SCHEDULE_QRA")
    value = _value("SCHEDULE_QRA", result_semantics={"schedule_method": "P6_WORK_CALENDAR", "unit": "DAYS"})
    assert "ENGINE_CAPABILITY_NOT_SUPPORTED" in qra_result_issues(row, value, now=datetime(2026, 10, 12))


def test_provider_summary_bounded_and_never_tail_certification():
    value = _value(
        histogram=list(range(10000)),
        cdf=list(range(10000)),
        sensitivity=list(range(10000)),
        runtime={"arrays": list(range(10000))},
    )
    summary = qra_summary(value, {"selected_percentiles": [90]})
    assert summary["selected_percentiles"] == [{"percentile": 90, "value": 900}]
    assert not {"histogram", "cdf", "sensitivity", "runtime"} & summary.keys()
    assert summary["tail_convergence_certified"] is False
    assert len(json.dumps(summary)) < 4000


def _qra_criterion(metric="PERCENTILE", analysis="COST_QRA"):
    row = criterion(
        "QRA-THRESHOLD",
        "Configured QRA criterion",
        "DECISION_HURDLE",
        "COST_QRA_RESULT" if analysis == "COST_QRA" else "SCHEDULE_QRA_RESULT",
        "source_payload",
        "LESS_THAN_OR_EQUAL" if metric == "PERCENTILE" else "GREATER_THAN_OR_EQUAL",
        1000 if metric == "PERCENTILE" else 0.8,
        blocking=True,
        required=True,
        order=1,
    )
    row["qra_criterion"] = {
        "metric": metric,
        "analysis_type": analysis,
        "percentile": 90,
        "currency": "USD",
        "target": {"source": "GATE_CRITERION", "value": 1000, "currency": "USD"},
    }
    return row


def _source(value):
    return {
        "evidence_type": "COST_QRA_RESULT" if value["analysis_type"] == "COST_QRA" else "SCHEDULE_QRA_RESULT",
        "scope_id": 14,
        "status": "VALID",
        "source_current": True,
        "source_hash": value["evidence_hash"],
        "source_payload": value,
    }


@pytest.mark.parametrize("metric,actual", [("PERCENTILE", 900), ("TARGET_PROBABILITY", 0.85)])
def test_criteria_consume_stored_percentile_or_probability_with_frozen_provenance(metric, actual):
    configured = _qra_criterion(metric)
    assert qra_criterion_issues(configured) == []
    results = evaluate_criteria(
        [configured],
        [_source(_value())],
        {},
        [_context()],
        policy_revision=2,
        policy_hash="p" * 64,
        evaluated_at="2026-10-12",
    )
    assert results[0]["result"] == "SATISFIED" and results[0]["source_value"] == actual
    assert results[0]["qra_evidence"]["target"]["source"] == "GATE_CRITERION"
    assert results[0]["qra_evidence"]["tail_convergence_certified"] is False
    assert "run_hash" in results[0]["qra_evidence"]


def test_probability_target_mismatch_and_currency_not_evaluable_no_calculation():
    row = _qra_criterion("TARGET_PROBABILITY")
    row["qra_criterion"]["target"]["value"] = 2000
    assert qra_criterion_value(row, _source(_value()))[0] is None
    row["qra_criterion"]["currency"] = "COP"
    assert qra_criterion_value(row, _source(_value()))[0] is None


def test_schedule_date_criterion_preserves_normalized_time_basis():
    row = _qra_criterion(analysis="SCHEDULE_QRA")
    target = "2026-12-01T00:00:00+00:00"
    row["expected_value"] = target
    row["qra_criterion"].update(
        unit="DAYS",
        time_basis="NORMALIZED_ELAPSED_TIME_V1",
        target={
            "source": "GATE_CRITERION",
            "value": target,
            "unit": "DAYS",
            "time_basis": "NORMALIZED_ELAPSED_TIME_V1",
        },
    )
    assert qra_criterion_issues(row) == []
    value = _value(
        "SCHEDULE_QRA",
        selected_percentiles=[{"percentile": 90, "value": 90, "completion_date": "2026-11-01T00:00:00+00:00"}],
        result_semantics={"unit": "DAYS", "schedule_method": "NORMALIZED_ELAPSED_TIME_V1"},
    )
    result = evaluate_criteria(
        [row], [_source(value)], {}, [_context()], policy_revision=2, policy_hash="p" * 64, evaluated_at="2026-10-12"
    )
    assert result[0]["result"] == "SATISFIED"
    value["result_semantics"]["schedule_method"] = "WORK_CALENDAR"
    assert qra_criterion_value(row, _source(value))[0] is None


@pytest.mark.parametrize("expected,result", [("900.0", "SATISFIED"), ("901", "NOT_SATISFIED")])
def test_qra_numeric_equals_normalizes_json_number_representation_only(expected, result):
    row = _qra_criterion()
    row["operator"] = "EQUALS"
    row["expected_value"] = expected
    row["qra_criterion"]["target"]["value"] = expected
    assert qra_criterion_issues(row) == []
    evaluated = evaluate_criteria(
        [row], [_source(_value())], {}, [_context()], policy_revision=2, policy_hash="p", evaluated_at="today"
    )[0]
    assert evaluated["result"] == result and evaluated["source_value"] == 900
    assert evaluated["threshold_or_expected_value"] == expected


@pytest.mark.parametrize(
    "target,expected_probability",
    [
        ("2026-12-01T00:00:00Z", 0.85),
        ("2026-11-30T19:00:00-05:00", 0.85),
        ("2026-12-01T00:00:01Z", None),
        ("not-an-instant", None),
    ],
)
def test_schedule_probability_target_uses_same_utc_instant_without_calendar_conversion(target, expected_probability):
    row = _qra_criterion("TARGET_PROBABILITY", "SCHEDULE_QRA")
    row["qra_criterion"].update(
        unit="HOURS",
        time_basis="NORMALIZED_ELAPSED_TIME_V1",
        target={
            "source": "GATE_CRITERION",
            "value": target,
            "unit": "HOURS",
            "time_basis": "NORMALIZED_ELAPSED_TIME_V1",
        },
    )
    value = _value(
        "SCHEDULE_QRA",
        target_probabilities={"probability_meeting_target_date": 0.85},
        result_semantics={
            "unit": "HOURS",
            "schedule_method": "NORMALIZED_ELAPSED_TIME_V1",
            "target_date": "2026-12-01T00:00:00+00:00",
        },
    )
    actual, details, warnings = qra_criterion_value(row, _source(value))
    assert actual == expected_probability and details["target"]["value"] == target
    assert bool(warnings) is (expected_probability is None)
    value["result_semantics"]["unit"] = "DAYS"
    assert qra_criterion_value(row, _source(value))[0] is None


@pytest.mark.parametrize(
    "target,result",
    [
        ("2026-11-01T00:00:00Z", "SATISFIED"),
        ("2026-10-31T19:00:00-05:00", "SATISFIED"),
        ("2026-11-01T00:00:01Z", "NOT_SATISFIED"),
    ],
)
def test_schedule_percentile_equals_uses_governed_utc_representation(target, result):
    row = _qra_criterion(analysis="SCHEDULE_QRA")
    row.update(operator="EQUALS", expected_value=target)
    row["qra_criterion"].update(
        unit="HOURS",
        time_basis="NORMALIZED_ELAPSED_TIME_V1",
        target={
            "source": "GATE_CRITERION",
            "value": target,
            "unit": "HOURS",
            "time_basis": "NORMALIZED_ELAPSED_TIME_V1",
        },
    )
    value = _value(
        "SCHEDULE_QRA",
        selected_percentiles=[{"percentile": 90, "value": 900, "completion_date": "2026-11-01T00:00:00+00:00"}],
        result_semantics={"unit": "HOURS", "schedule_method": "NORMALIZED_ELAPSED_TIME_V1"},
    )
    assert qra_criterion_issues(row) == []
    evaluated = evaluate_criteria(
        [row], [_source(value)], {}, [_context()], policy_revision=2, policy_hash="p", evaluated_at="today"
    )[0]
    assert evaluated["result"] == result
    assert evaluated["qra_evidence"]["tail_convergence_certified"] is False


def test_business_case_qra_strict_consistency_reuses_cross_source_mismatch():
    rows = [
        {
            "evidence_type": "BUSINESS_CASE_READINESS",
            "scope_id": 14,
            "source_payload": {"source_hashes": {"cost_qra_result": "old"}},
        },
        {
            "evidence_type": "COST_QRA_RESULT",
            "scope_id": 14,
            "source_hash": "new",
            "bc_consistency_required": True,
            "qra_applicability": {"required": True},
        },
    ]
    consistency = InvestmentGatePreparationService._cross_source_consistency(rows)
    assert consistency[0]["status"] == "MISMATCH"
    assert InvestmentGatePreparationService._cross_source_findings("PYP-FFA", consistency)[0] == [
        "CROSS_SOURCE_MISMATCH:cost_qra_result"
    ]
    rows[1]["bc_consistency_required"] = False
    assert InvestmentGatePreparationService._cross_source_consistency(rows) == []


@pytest.mark.parametrize("source_key", ["fel", "risk"])
@pytest.mark.parametrize("change", ["same", "hash", "record", "missing_record", "project", "manual"])
def test_bc_consistency_compares_trusted_native_project_source_not_readiness_wrapper(source_key, change):
    reference = {"project_workspace_id": 14}
    if source_key == "fel":
        reference.update(status_id=71, definition_source_hash="native-hash")
        payload = {"project_source_reference": reference}
        evidence_type = "PROJECT_DEFINITION_READINESS"
    else:
        reference.update(assessment_id=71, risk_readiness_hash="native-hash", assessment_hash="native-hash")
        payload = {"project_source_references": [reference]}
        evidence_type = "RISK_READINESS"
    if change == "hash":
        reference["definition_source_hash" if source_key == "fel" else "risk_readiness_hash"] = "different-native"
    elif change == "record":
        reference["status_id" if source_key == "fel" else "assessment_id"] = 72
    elif change == "missing_record":
        reference["status_id" if source_key == "fel" else "assessment_id"] = None
    elif change == "project":
        reference["project_workspace_id"] = 99
    rows = [
        {
            "evidence_type": "BUSINESS_CASE_READINESS",
            "scope_id": 14,
            "source_payload": {
                "source_hashes": {source_key: "native-hash"},
                "source_references": {source_key: {"id": 71}},
            },
        },
        {
            "evidence_type": evidence_type,
            "scope_id": 14 if source_key == "fel" else None,
            "source_hash": "authoritative-readiness-wrapper-or-aggregate",
            "evidence_origin": "MANUAL" if change == "manual" else "GOVERNED_SOURCE",
            "source_payload": {**payload, "evidence_origin": "GOVERNED_SOURCE"},
        },
    ]
    before = deepcopy(rows)
    result = InvestmentGatePreparationService._cross_source_consistency(rows)[0]
    assert result["status"] == (
        "CONSISTENT"
        if change == "same"
        else "SOURCE_MISSING"
        if source_key == "risk" and change == "project"
        else "MISMATCH"
    )
    assert result["provider_evidence_hash"] == "authoritative-readiness-wrapper-or-aggregate"
    assert rows == before
    if change == "manual":
        assert result["hash_basis"] == "PROVIDER_EVIDENCE_HASH"
        assert result["actual_hash"] == rows[1]["source_hash"]
    else:
        assert result["hash_basis"] in {"PROJECT_FEL_STATUS_DEFINITION_SOURCE", "PROJECT_RISK_READINESS_ASSESSMENT"}


def test_legacy_consistency_without_canonical_references_retains_original_hash_basis():
    rows = [
        {
            "evidence_type": "BUSINESS_CASE_READINESS",
            "scope_id": 14,
            "source_payload": {"source_hashes": {"fel": "same"}},
        },
        {
            "evidence_type": "PROJECT_DEFINITION_READINESS",
            "scope_id": 14,
            "source_hash": "same",
            "evidence_origin": "GOVERNED_SOURCE",
            "source_payload": {},
        },
    ]
    result = InvestmentGatePreparationService._cross_source_consistency(rows)[0]
    assert result["status"] == "CONSISTENT" and result["hash_basis"] == "PROVIDER_EVIDENCE_HASH"


def test_bc_consistency_duplicate_native_risk_references_fail_closed():
    reference = {"project_workspace_id": 14, "assessment_id": 71, "risk_readiness_hash": "native"}
    rows = [
        {
            "evidence_type": "BUSINESS_CASE_READINESS",
            "scope_id": 14,
            "source_payload": {
                "source_hashes": {"risk": "native"},
                "source_references": {"risk": {"id": 71}},
            },
        },
        {
            "evidence_type": "RISK_READINESS",
            "scope_id": None,
            "source_hash": "aggregate",
            "evidence_origin": "GOVERNED_SOURCE",
            "source_payload": {"project_source_references": [reference, deepcopy(reference)]},
        },
    ]
    result = InvestmentGatePreparationService._cross_source_consistency(rows)[0]
    assert result["status"] == "SOURCE_MISSING"
    assert result["actual_hash"] is None
    assert result["provider_evidence_hash"] == "aggregate"


@pytest.mark.parametrize(
    "material_change",
    [None, "definition_readiness_hash", "assessment_id", "readiness_status", "source_current", "FEL_stage_code"],
)
def test_gate_native_enrichment_preserves_v1_material_context_but_real_fel_changes_do_not(monkeypatch, material_change):
    db = MagicMock()
    db.scalar.return_value = None
    project = SimpleNamespace(id=14, defaults_json={"_project": {"project_type": "COMMERCIAL"}})
    core = {
        "definition_readiness_hash": "existing-wrapper-hash",
        "assessment_id": 71,
        "readiness_status": "READY",
        "source_current": True,
        "FEL_stage_code": "FEL-3",
    }
    contract = InvestmentGateEvidenceOut.model_construct(**core)
    monkeypatch.setattr(ProjectDefinitionService, "investment_gate_evidence", lambda self, project_id: contract)
    service = BasicDataService(db, 1, 1)
    legacy_context = service._context(project)
    legacy_provider = contract.model_dump(mode="json", exclude={"project_source_reference"})
    assert legacy_context["fel_provider_context"] == legacy_provider
    legacy_material = QraFoundationService._material({"context": legacy_context})
    contract.project_source_reference = {
        "project_workspace_id": 14,
        "status_id": 9,
        "status_revision": 3,
        "definition_source_hash": "native-source-hash",
        "definition_readiness_hash": core["definition_readiness_hash"],
    }
    enriched_context = service._context(project)
    assert enriched_context == legacy_context
    assert QraFoundationService._material({"context": enriched_context}) == legacy_material
    if material_change:
        setattr(
            contract,
            material_change,
            {
                "definition_readiness_hash": "changed-hash",
                "assessment_id": 72,
                "readiness_status": "BLOCKED",
                "source_current": False,
                "FEL_stage_code": "FEL-2",
            }[material_change],
        )
        changed_context = service._context(project)
        assert QraFoundationService._material({"context": changed_context}) != legacy_material
        assert changed_context["fel_provider_context"][material_change] == getattr(contract, material_change)


def test_frozen_evidence_never_resolves_new_provider_and_current_preparation_becomes_stale():
    service = InvestmentGatePreparationService(MagicMock(), 1, 1)
    item = SimpleNamespace(status="VALID", scope_reference_hash=None, valid_until=None, source_hash="old")
    assert service._qra_evidence_status(item, SimpleNamespace(status="FROZEN"), _qra_requirement()) == "VALID"


def test_class_c_qra_criterion_not_blocking_missing_result():
    source = _source(_value())
    source["status"] = "NOT_REQUIRED"
    source["qra_applicability"] = {"outcome": "NOT_REQUIRED"}
    source["source_payload"] = {}
    results = evaluate_criteria(
        [_qra_criterion()], [source], {}, [_context()], policy_revision=2, policy_hash="p", evaluated_at="today"
    )
    assert results[0]["result"] == "NOT_APPLICABLE"
    assert results[0]["warnings"] == []
    assert results[0]["qra_evidence"]["qra_applicability"]["outcome"] == "NOT_REQUIRED"


@pytest.mark.parametrize("currency,expected", [("USD", "NOT_APPLICABLE"), ("COP", "NOT_EVALUABLE")])
def test_conditional_value_band_hurdle_preserves_optional_vs_unknown_context(currency, expected):
    requirement = apply_qra_context(
        _qra_requirement(
            applicability="CONDITIONAL",
            value_band={"source": "PROJECT_CREATION_ESTIMATED_BUDGET", "currency": "USD", "minimum": 2000000},
        ),
        _context(estimated_budget=1000000, currency_code=currency),
    )
    source = _source(_value())
    source["qra_applicability"] = requirement["qra_applicability"]
    source["status"] = "NOT_REQUIRED" if requirement["classification"] == "C" else "NOT_AVAILABLE"
    configured = _qra_criterion()
    configured["criterion_type"] = "MUST_MEET"
    results = evaluate_criteria(
        [configured], [source], {}, [_context()], policy_revision=2, policy_hash="p", evaluated_at="today"
    )
    assert results[0]["result"] == expected
    assert results[0]["blocking"] is True
    assert results[0]["qra_evidence"]["qra_applicability"] == requirement["qra_applicability"]
    if expected == "NOT_APPLICABLE":
        assert "OUTSIDE_CONFIGURED_VALUE_BAND" in requirement["qra_applicability"]["reasons"]
    else:
        assert "QRA_VALUE_NOT_COMPARABLE_NO_SILENT_FX" in requirement["qra_applicability"]["reasons"]


def test_freshness_does_not_silently_accept_future_or_missing_date():
    row = _qra_requirement(freshness_days=30)
    now = datetime(2026, 10, 12)
    assert "QRA_EVIDENCE_EXPIRED" in qra_result_issues(
        row, _value(as_of=(now + timedelta(days=1)).isoformat()), now=now
    )
    assert "QRA_FRESHNESS_NOT_EVALUABLE" in qra_result_issues(row, _value(as_of=None), now=now)


def test_configured_policy_author_publisher_sod_prevents_publish_without_new_role():
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 7)
    record = SimpleNamespace(
        id=20,
        status="draft",
        version=1,
        created_by_user_id=7,
        content_json={**deepcopy(DEFAULT_POLICY), "sod": {"author_must_differ_from_publisher": True}},
    )
    service._configuration = MagicMock(return_value=record)
    service.db.scalars.return_value.all.return_value = []
    with pytest.raises(HTTPException) as error:
        service.publish_configuration(20, 1)
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "POLICY_AUTHOR_PUBLISHER_SOD_VIOLATION"
    service.db.commit.assert_not_called()
    assert record.status == "draft" and record.version == 1


def test_published_content_and_etag_cannot_be_rewritten():
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 7)
    record = SimpleNamespace(id=20, status="published", version=2)
    service._configuration = MagicMock(return_value=record)
    with pytest.raises(HTTPException) as error:
        service.update_configuration(20, 2, "A name", "", deepcopy(DEFAULT_POLICY))
    assert error.value.status_code == 409 and error.value.detail["code"] == "PUBLISHED_POLICY_IMMUTABLE"
    with pytest.raises(HTTPException) as error:
        service.update_configuration(20, 1, "A name", "", deepcopy(DEFAULT_POLICY))
    assert error.value.status_code == 412
    service.db.commit.assert_not_called()


def test_clone_idempotency_replays_payload_bound_event_and_rejects_other_actor():
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 7)
    source = SimpleNamespace(id=20, version=1)
    clone = SimpleNamespace(id=21)
    service._configuration = MagicMock(side_effect=lambda identifier, **_: source if identifier == 20 else clone)
    event = SimpleNamespace(
        target_id=21,
        metadata_json={
            "idempotency_key": "same-key-123",
            "request_hash": _hash({"source_id": 20, "expected_version": 1, "actor_id": 7}),
        },
    )
    service.db.scalars.return_value.all.return_value = [event]
    assert service.clone_configuration(20, 1, "same-key-123") is clone
    service.db.add.assert_not_called()
    service.actor_id = 8
    with pytest.raises(HTTPException) as error:
        service.clone_configuration(20, 1, "same-key-123")
    assert error.value.status_code == 409


def test_qualified_resolver_preserves_accepted_stale_identity_but_never_satisfies(monkeypatch):
    from app.modules.qra_engine.service import QraEngineService

    value = _value(source_current=False, evidence_hash=None, blockers=["QRA_MODEL_STALE"])
    monkeypatch.setattr(QraEngineService, "provider_evidence", lambda *_a, **_k: deepcopy(value))
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    payload, error = service.resolve_governed_payload(_qra_requirement(), {}, 14)
    assert error == "SOURCE_STALE" and payload["source_current"] is False
    assert payload["evidence_hash"] == value["acceptance_hash"]
    assert payload["qra_summary"]["run_hash"] == value["run_hash"]


def test_qualified_resolver_unaccepted_and_wrong_type_never_satisfy(monkeypatch):
    from app.modules.qra_engine.service import QraEngineService

    monkeypatch.setattr(QraEngineService, "provider_evidence", lambda *_a, **_k: _value(acceptance_hash=None))
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    assert service.resolve_governed_payload(_qra_requirement(), {}, 14) == (None, "SOURCE_EVIDENCE_UNAVAILABLE")
    monkeypatch.setattr(QraEngineService, "provider_evidence", lambda *_a, **_k: _value("SCHEDULE_QRA"))
    payload, error = service.resolve_governed_payload(_qra_requirement(), {}, 14)
    assert error == "QRA_ANALYSIS_TYPE_MISMATCH"
    assert "QRA_ANALYSIS_TYPE_MISMATCH" in payload["blockers"]


def test_engine_incapability_is_distinct_from_missing_provider(monkeypatch):
    from app.modules.qra_engine.service import QraEngineService

    monkeypatch.setattr(QraEngineService, "provider_evidence", lambda *_a, **_k: {"status": "UNAVAILABLE"})
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    service._schedule_context_unsupported = MagicMock(return_value=True)
    payload, error = service.resolve_governed_payload(_qra_requirement("SCHEDULE_QRA"), {}, 14)
    assert payload is None and error == "ENGINE_CAPABILITY_NOT_SUPPORTED"
    assert PROVIDER_REGISTRY["QRA_RESULT_PROVIDER"]["status"] == "AVAILABLE"


@pytest.mark.parametrize(
    "status,unsupported",
    [
        ("Not Started", False),
        ("NOT_STARTED", False),
        ("TK_NotStart", False),
        ("not-started", False),
        ("In Progress", True),
        ("Completed", True),
    ],
)
def test_schedule_capability_uses_same_source_status_normalization_as_released_kernel(monkeypatch, status, unsupported):
    from app.modules.qra_foundation.adapters import SourceAdapters

    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    service._projects = MagicMock(return_value=[SimpleNamespace(id=14)])
    monkeypatch.setattr(SourceAdapters, "operational_project", lambda *_a: SimpleNamespace(id=1))
    service.db.scalar.return_value = {"activities": [{"activity_status": status}]}
    assert service._schedule_context_unsupported(14) is unsupported


def test_stale_accepted_schedule_keeps_currentness_separate_from_engine_incapability(monkeypatch):
    from app.modules.qra_engine.service import QraEngineService

    value = _value(
        "SCHEDULE_QRA",
        source_current=False,
        blockers=["QRA_MODEL_STALE"],
        result_semantics={"unit": "HOURS", "schedule_method": "NORMALIZED_ELAPSED_TIME_V1"},
    )
    monkeypatch.setattr(QraEngineService, "provider_evidence", lambda *_a, **_k: deepcopy(value))
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    service._schedule_context_unsupported = MagicMock(return_value=True)
    payload, error = service.resolve_governed_payload(_qra_requirement("SCHEDULE_QRA"), {}, 14)
    assert error == "ENGINE_CAPABILITY_NOT_SUPPORTED"
    assert payload["source_current"] is False and payload["qra_summary"]["run_hash"] == value["run_hash"]
    assert payload["qra_applicability"]["capability_fit"] == "NOT_SUPPORTED"
    assert {"QRA_MODEL_STALE", "ENGINE_CAPABILITY_NOT_SUPPORTED"}.issubset(payload["blockers"])


def test_current_gate_becomes_stale_on_supersession_without_mutating_old_refs(monkeypatch):
    monkeypatch.setattr(
        InvestmentEvidencePolicyService,
        "resolve_governed_payload",
        lambda *_args: ({"evidence_hash": "new", "source_current": True}, None),
    )
    gate = InvestmentGatePreparationService(MagicMock(), 1, 1)
    item = SimpleNamespace(status="VALID", valid_until=None, scope_reference_hash=None, source_hash="old", scope_id=14)
    record = SimpleNamespace(status="DRAFT", source_snapshot_json={})
    assert gate._qra_evidence_status(item, record, _qra_requirement()) == "STALE"
    assert item.source_hash == "old" and item.status == "VALID"
    for status in ("FROZEN", "SUPERSEDED", "VOIDED"):
        record.status = status
        assert gate._qra_evidence_status(item, record, _qra_requirement()) == "VALID"


def test_stale_qra_blocks_project_coverage_as_well_as_overall_readiness():
    gate = InvestmentGatePreparationService(MagicMock(), 1, 1)
    requirement = _qra_requirement()
    item = SimpleNamespace(
        requirement_key=requirement["requirement_key"], evidence_type="COST_QRA_RESULT", scope_id=14, status="VALID"
    )
    record = SimpleNamespace(id=1, status="DRAFT", source_snapshot_json={"selected_project_ids": [14]})
    gate._evidence_records = MagicMock(return_value=[item])
    gate._qra_evidence_status = MagicMock(return_value="STALE")
    gate._effective_evidence_status = MagicMock(return_value="VALID")
    value = gate._project_readiness(record, {"requirements": [requirement]})
    assert value.coverage_percent == 0 and value.valid_project_count == 0 and value.blocked_project_count == 1
    assert value.projects[0]["missing_requirements"] == [requirement["requirement_key"]]


def test_engine_incapability_does_not_hide_stale_source_currentness_on_gate(monkeypatch):
    monkeypatch.setattr(
        InvestmentEvidencePolicyService,
        "resolve_governed_payload",
        lambda *_args: ({"evidence_hash": "old", "source_current": False}, "ENGINE_CAPABILITY_NOT_SUPPORTED"),
    )
    gate = InvestmentGatePreparationService(MagicMock(), 1, 1)
    item = SimpleNamespace(status="VALID", valid_until=None, scope_reference_hash=None, source_hash="old", scope_id=14)
    record = SimpleNamespace(status="DRAFT", source_snapshot_json={})
    assert gate._qra_evidence_status(item, record, _qra_requirement("SCHEDULE_QRA")) == "STALE"
    assert item.status == "VALID" and item.source_hash == "old"


def test_controlled_range_has_governed_bound_provenance():
    row = _qra_criterion()
    row["operator"] = "WITHIN_RANGE"
    row["expected_value"] = [800, 1000]
    row["qra_criterion"]["target"]["value"] = [800, 1000]
    assert qra_criterion_issues(row) == []
    results = evaluate_criteria(
        [row], [_source(_value())], {}, [_context()], policy_revision=2, policy_hash="p", evaluated_at="today"
    )
    assert results[0]["result"] == "SATISFIED"
    row["expected_value"] = [1000, 800]
    row["qra_criterion"]["target"]["value"] = [1000, 800]
    assert "INVALID_QRA_CONTROLLED_RANGE" in qra_criterion_issues(row)


def test_schedule_controlled_date_range_has_ordered_explicit_bounds():
    row = _qra_criterion(analysis="SCHEDULE_QRA")
    row["operator"] = "WITHIN_RANGE"
    row["expected_value"] = ["2026-12-01T00:00:00Z", "2026-11-01T00:00:00Z"]
    row["qra_criterion"].update(
        unit="DAYS",
        time_basis="NORMALIZED_ELAPSED_TIME_V1",
        target={
            "source": "GATE_CRITERION",
            "value": row["expected_value"],
            "unit": "DAYS",
            "time_basis": "NORMALIZED_ELAPSED_TIME_V1",
        },
    )
    assert "INVALID_QRA_CONTROLLED_RANGE" in qra_criterion_issues(row)
    row["expected_value"].reverse()
    assert qra_criterion_issues(row) == []


@pytest.mark.parametrize("malformed", ["policy", "criterion", "percentiles"])
def test_malformed_qra_configuration_returns_controlled_422_not_attribute_error(malformed):
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    content = deepcopy(DEFAULT_POLICY)
    row, criterion_row = _qra_requirement(), _qra_criterion()
    if malformed == "policy":
        row["qra_policy"] = ["not an object"]
    elif malformed == "criterion":
        criterion_row["qra_criterion"] = ["not an object"]
    else:
        row["qra_policy"]["selected_percentiles"] = 90
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(row)
    content.setdefault("decision_criterion_policy", {}).setdefault("criteria_by_profile", {})["PYP-FFA"] = [
        criterion_row
    ]
    with pytest.raises(HTTPException) as error:
        service._validate_policy(content)
    assert error.value.status_code == 422 and error.value.detail["code"] == "INVALID_EVIDENCE_POLICY"


@pytest.mark.parametrize("invalid_override", ["integrated", "manual", "schedule-capability"])
def test_project_type_override_cannot_bypass_qra_publication_guardrails(invalid_override):
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    content = deepcopy(DEFAULT_POLICY)
    row = _qra_requirement("SCHEDULE_QRA" if invalid_override == "schedule-capability" else "COST_QRA")
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(row)
    override = {
        "gate_profile_code": "PYP-FFA",
        "evidence_type": row["evidence_type"],
        "classification": "A",
        "project_type_filter": ["COMMERCIAL"],
    }
    if invalid_override == "integrated":
        override["qra_policy"] = {**row["qra_policy"], "analysis_type": "INTEGRATED_COST_SCHEDULE_QRA"}
    elif invalid_override == "manual":
        override["allow_manual_reference"] = True
    else:
        override["qra_policy"] = {**row["qra_policy"], "capability_requirements": {}}
    content["project_type_overrides"].append(override)
    with pytest.raises(HTTPException) as error:
        service._validate_policy(content)
    assert error.value.status_code == 422
    assert any("PROJECT_TYPE_OVERRIDE" in issue for issue in error.value.detail["issues"])
