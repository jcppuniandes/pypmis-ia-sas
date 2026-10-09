"""Command-line entry point for controlled Enterprise Structure gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.database.session import SessionLocal
from app.modules.enterprise_structure.importer.apply import CoreApplyError, apply_core
from app.modules.enterprise_structure.importer.inventory import capture_fingerprints, capture_inventory
from app.modules.enterprise_structure.importer.parser import ConfigurationParseError, parse_configuration
from app.modules.enterprise_structure.importer.publish import CorePublishError, publish_core
from app.modules.enterprise_structure.importer.report import (
    render_apply_human,
    render_apply_json,
    render_human,
    render_json,
    render_publish_human,
    render_publish_json,
)
from app.modules.enterprise_structure.importer.schema import canonical_json_schema
from app.modules.enterprise_structure.importer.snapshot import load_tenant_snapshot
from app.modules.enterprise_structure.importer.validator import build_dry_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P&Pmis Nivel 2B Enterprise Structure importer")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Parse, validate and diff without mutating the database")
    validate.add_argument("--file", required=True, help="Canonical YAML input")
    validate.add_argument("--tenant", required=True, help="Target tenant slug/code")
    validate.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    validate.add_argument("--output", help="Optional report file; stdout is always supported")
    preflight = commands.add_parser("preflight", help="Capture protected inventory and deterministic fingerprints")
    preflight.add_argument("--tenant", required=True, help="Target tenant slug/code")
    preflight.add_argument("--inventory-output", required=True, help="Inventory JSON output")
    preflight.add_argument("--fingerprints-output", required=True, help="Fingerprints JSON output")
    apply = commands.add_parser("apply", help="Apply an explicitly approved CORE release in one transaction")
    apply.add_argument("--file", required=True, help="Canonical YAML input")
    apply.add_argument("--tenant", required=True, help="Current or approved tenant slug")
    apply.add_argument("--expected-hash", required=True, help="Approved raw YAML SHA-256")
    apply.add_argument("--expected-source-hash", required=True, help="Approved preflight source SHA-256")
    apply.add_argument("--actor", required=True, help="Existing active authorized user email")
    apply.add_argument("--approved-tenant-name", required=True, help="Exact approved final tenant name")
    apply.add_argument("--approved-tenant-slug", required=True, help="Exact approved final tenant slug")
    apply.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    apply.add_argument("--output", help="Optional report file; stdout is always supported")
    apply.add_argument("--json-output", help="Optional JSON evidence file written from the same transaction")
    apply.add_argument("--human-output", help="Optional human evidence file written from the same transaction")
    publish = commands.add_parser("publish", help="Publish the approved, already-applied CORE release")
    publish.add_argument("--file", required=True, help="Canonical YAML input")
    publish.add_argument("--tenant", required=True, help="Exact target tenant slug")
    publish.add_argument("--release", required=True, help="Exact approved release code")
    publish.add_argument("--expected-hash", required=True, help="Approved raw YAML SHA-256")
    publish.add_argument("--expected-canonical-hash", required=True, help="Approved canonical SHA-256")
    publish.add_argument("--expected-source-hash", required=True, help="Approved prepublish source SHA-256")
    publish.add_argument("--actor", required=True, help="Existing active authorized user email")
    publish.add_argument("--approved", action="store_true", help="Explicitly approve this publish transaction")
    publish.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    publish.add_argument("--output", help="Optional report file; stdout is always supported")
    publish.add_argument("--json-output", help="Optional JSON evidence file")
    publish.add_argument("--human-output", help="Optional human evidence file")
    schema = commands.add_parser("schema", help="Emit the canonical JSON Schema")
    schema.add_argument("--output", help="Optional schema file; stdout is always supported")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "schema":
        rendered_schema = json.dumps(canonical_json_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            Path(args.output).write_text(rendered_schema, encoding="utf-8")
        print(rendered_schema, end="")
        return 0
    if args.command == "preflight":
        try:
            with SessionLocal() as db:
                inventory = capture_inventory(db)
                fingerprints = capture_fingerprints(db)
                normalized_tenant = args.tenant.strip().lower().replace("_", "-")
                if not any(
                    str(item.get("slug", "")).lower().replace("_", "-") == normalized_tenant
                    for item in inventory["tables"]["tenants"]
                ):
                    raise LookupError(f"Tenant not found: {args.tenant}")
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        inventory_rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fingerprints_rendered = json.dumps(fingerprints, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        Path(args.inventory_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.fingerprints_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.inventory_output).write_text(inventory_rendered, encoding="utf-8")
        Path(args.fingerprints_output).write_text(fingerprints_rendered, encoding="utf-8")
        print(fingerprints_rendered, end="")
        return 0
    try:
        configuration = parse_configuration(args.file)
    except ConfigurationParseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.command == "apply":
        try:
            with SessionLocal() as db, db.begin():
                report = apply_core(
                    db,
                    configuration,
                    source_file=args.file,
                    tenant_code=args.tenant,
                    expected_hash=args.expected_hash,
                    expected_source_hash=args.expected_source_hash,
                    actor_email=args.actor,
                    approved_tenant_name=args.approved_tenant_name,
                    approved_tenant_slug=args.approved_tenant_slug,
                )
        except (CoreApplyError, LookupError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        rendered_json = render_apply_json(report)
        rendered_human = render_apply_human(report)
        rendered = rendered_json if args.json else rendered_human
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        if args.json_output:
            Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_output).write_text(rendered_json, encoding="utf-8")
        if args.human_output:
            Path(args.human_output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.human_output).write_text(rendered_human, encoding="utf-8")
        print(rendered, end="")
        return 0
    if args.command == "publish":
        try:
            with SessionLocal() as db, db.begin():
                report = publish_core(
                    db,
                    configuration,
                    source_file=args.file,
                    tenant_code=args.tenant,
                    release_code=args.release,
                    expected_hash=args.expected_hash,
                    expected_canonical_hash=args.expected_canonical_hash,
                    expected_source_hash=args.expected_source_hash,
                    actor_email=args.actor,
                    approved=args.approved,
                )
        except (CorePublishError, LookupError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        rendered_json = render_publish_json(report)
        rendered_human = render_publish_human(report)
        rendered = rendered_json if args.json else rendered_human
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        if args.json_output:
            Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_output).write_text(rendered_json, encoding="utf-8")
        if args.human_output:
            Path(args.human_output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.human_output).write_text(rendered_human, encoding="utf-8")
        print(rendered, end="")
        return 0
    try:
        with SessionLocal() as db:
            snapshot = load_tenant_snapshot(
                db,
                args.tenant,
                configuration.metadata.requested_by,
            )
            report = build_dry_run(configuration, snapshot)
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    rendered = render_json(report) if args.json else render_human(report)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
