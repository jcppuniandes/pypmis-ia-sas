"""Command-line entry point for the non-mutating Nivel 2B validation phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.database.session import SessionLocal
from app.modules.enterprise_structure.importer.parser import ConfigurationParseError, parse_configuration
from app.modules.enterprise_structure.importer.report import render_human, render_json
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
    try:
        configuration = parse_configuration(args.file)
    except ConfigurationParseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
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
