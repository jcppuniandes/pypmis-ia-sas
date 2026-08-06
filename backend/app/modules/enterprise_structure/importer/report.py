"""Human and JSON renderers for Nivel 2B dry-run evidence."""

import json

from app.modules.enterprise_structure.importer.models import DryRunReport, Severity


def render_json(report: DryRunReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)


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
        lines.append(f"  {item.action.value:9} {item.entity:22} {item.key} - {item.reason}")
    lines.extend(["", "Topological order", "  " + " -> ".join(report.topological_order)])
    return "\n".join(lines) + "\n"
