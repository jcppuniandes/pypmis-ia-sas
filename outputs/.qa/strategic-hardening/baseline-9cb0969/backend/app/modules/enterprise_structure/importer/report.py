"""Human and JSON renderers for Nivel 2B dry-run evidence."""

import json

from app.modules.enterprise_structure.importer.models import (
    CoreApplyReport,
    CorePublishReport,
    DryRunReport,
    Severity,
)


def render_json(report: DryRunReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)


def render_apply_json(report: CoreApplyReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_apply_human(report: CoreApplyReport) -> str:
    lines = [
        "P&Pmis Controlled CORE Apply",
        f"Release: {report.release_code}",
        f"Tenant: {report.tenant_code}",
        f"Actor: {report.actor}",
        f"Result: {report.outcome}",
        f"Idempotent replay: {'YES' if report.idempotent_replay else 'NO'}",
        f"Input SHA-256: {report.input_hash}",
        f"Source snapshot SHA-256: {report.source_snapshot_hash}",
        "",
        "Summary",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(report.summary.items()))
    lines.extend(
        [
            "",
            "Tenant identity",
            f"- id: {report.tenant_change.tenant_id}",
            f"- name: {report.tenant_change.old_name} -> {report.tenant_change.new_name}",
            f"- slug: {report.tenant_change.old_slug} -> {report.tenant_change.new_slug}",
            f"- currency: {report.tenant_change.currency}",
            "",
            "Workspaces",
        ]
    )
    lines.extend(
        "- "
        f"{item.action.value.upper():9} id={item.id:<3} {item.external_key:<18} "
        f"{item.record_code:<16} {item.workspace_type:<14} {item.name}"
        for item in report.workspaces
    )
    lines.extend(
        [
            "",
            f"Audit SecurityEvent: {report.audit_event_id}",
            "Publish CORE: NOT EXECUTED",
        ]
    )
    return "\n".join(lines) + "\n"


def render_publish_json(report: CorePublishReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_publish_human(report: CorePublishReport) -> str:
    lines = [
        "P&Pmis Controlled CORE Publish",
        f"Release: {report.release_code}",
        f"Tenant: {report.tenant_id} · {report.tenant_code}",
        f"Actor: {report.actor}",
        f"Result: {report.outcome}",
        f"State: {report.state}",
        f"Mutations: {report.mutation_count}",
        f"Raw SHA-256: {report.input_hash}",
        f"Canonical SHA-256: {report.canonical_input_hash}",
        f"Content fingerprint: {report.content_fingerprint}",
        "",
        "Published snapshot",
        f"- Workspaces: {report.workspace_count}",
        f"- Strategic Objectives: {report.objective_count}",
        f"- Classifications: {report.classification_count}",
        f"- Links: {report.link_count}",
        f"- Operational statuses: {report.operational_statuses}",
        "- Operational status transitions: NONE",
        f"- SecurityEvent: {report.audit_event_id if report.audit_event_id is not None else 'NONE (safe replay)'}",
        f"- Published at: {report.published_at.isoformat()}",
    ]
    return "\n".join(lines) + "\n"


def render_human(report: DryRunReport) -> str:
    lines = [
        "P&Pmis Enterprise Structure - Nivel 2B dry-run",
        f"Tenant: {report.tenant_code}",
        f"Release: {report.release_code}",
        f"Input hash: {report.input_hash}",
        f"Result: {'VALID' if report.valid else 'BLOCKED'}",
        "",
        "Summary",
    ]
    for key, value in report.summary.items():
        lines.append(f"  {key}: {value}")
    lines.extend(["", "Findings"])
    if not report.findings:
        lines.append("  No findings.")
    for item in report.findings:
        marker = "!" if item.severity == Severity.ERROR else "~" if item.severity == Severity.WARNING else "i"
        lines.append(f"  [{marker}] {item.severity.value} {item.code} {item.section}/{item.reference}")
        lines.append(f"      {item.message}")
        lines.append(f"      Recommendation: {item.recommendation}")
    lines.extend(["", "Diff"])
    for item in report.diff:
        record_code = f" [{item.record_code}]" if item.record_code else ""
        adoption = f" existing_id={item.existing_id} old={item.old_record_code}" if item.existing_id else ""
        lines.append(f"  {item.action.value:9} {item.entity:22} {item.key}{record_code}{adoption} - {item.reason}")
    lines.extend(["", "Topological order", "  " + " -> ".join(report.topological_order)])
    return "\n".join(lines) + "\n"
