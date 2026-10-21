"""Reproducible, read-only static inventory of legacy Project dependencies.

Does not import application modules, connect to a database or infer identity from
numeric equality. Function candidates are explicitly labelled static evidence;
runtime reachability is not asserted by this inventory.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/validation/wave-o1a-20261019/legacy-consumer-inventory.json"
PROJECT_TOKEN = re.compile(
    r"\b(?:project_id|operational_project_id|legacy_project_id)\b|\bProject\b"
)


def disposition(path: str, symbol: str, *, read: bool = False) -> str:
    value = f"{path} {symbol}".lower()
    if "schedule_parser.py" in value:
        return "DEPRECATION_CANDIDATE"
    if "qra_foundation/adapters" in value:
        return "READ_ONLY_LEGACY"
    if any(
        word in value
        for word in (
            "documents",
            "rfq",
            "contract",
            "procure",
            "claim",
            "integrated_control",
        )
    ):
        return "MIGRATE_LATER"
    if any(
        word in value
        for word in (
            "quantity",
            "bim",
            "schedule",
            "control_account",
            "cost",
            "progress",
            "baseline",
            "wbs",
        )
    ):
        return "READ_ONLY_LEGACY" if read else "MIGRATE_IN_O1B"
    if "seed" in value or "bootstrap" in value:
        return "KEEP_BEHIND_ADAPTER"
    return "READ_ONLY_LEGACY" if read else "KEEP_BEHIND_ADAPTER"


def source_authority(path: str) -> str:
    if "qra_foundation/adapters" in path:
        return "Canonical Workspace selects an explicit legacy source; strategic aggregate remains read-only."
    return "Legacy projects.id is an operational aggregate only; enterprise_workspaces PROJECT remains canonical identity."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--include-o1a", action="store_true")
    args = parser.parse_args()
    model_path = ROOT / "backend/app/domain/models.py"
    model_source = model_path.read_text(encoding="utf-8")
    tree = ast.parse(model_source)
    foreign_keys: list[dict] = []
    legacy_entities = {"Project"}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        table = ""
        for statement in node.body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__tablename__"
                for t in statement.targets
            ):
                table = ast.literal_eval(statement.value)
            fragment = ast.get_source_segment(model_source, statement) or ""
            if (
                'ForeignKey("projects.id"' in fragment
                or "ForeignKey('projects.id'" in fragment
            ):
                legacy_entities.add(node.name)
                foreign_keys.append(
                    {
                        "id": f"FK-{len(foreign_keys) + 1:03}",
                        "path": "backend/app/domain/models.py",
                        "line": statement.lineno,
                        "symbol": node.name,
                        "table": table,
                        "target": "projects.id",
                        "awareness": "LEGACY_ONLY",
                        "migration": disposition("models", node.name),
                        "authority": source_authority("models"),
                    }
                )

    consumers: list[dict] = []
    snapshots: list[dict] = []
    excluded_new = "backend/app/modules/operational_context/"
    for path in sorted((ROOT / "backend/app").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(excluded_new) and not args.include_o1a:
            continue
        source = path.read_text(encoding="utf-8-sig")
        source_lines = source.splitlines()
        snapshots.append(
            {"path": relative, "sha256": hashlib.sha256(source.encode()).hexdigest()}
        )
        parsed = ast.parse(source)
        imported = {
            alias.name
            for item in ast.walk(parsed)
            if isinstance(item, ast.ImportFrom)
            and item.module
            and item.module.endswith("domain.models")
            for alias in item.names
        }
        if relative.endswith("domain/models.py"):
            continue
        for node in ast.walk(parsed):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fragment = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])
            symbols = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
            routes: list[dict] = []
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.args
                ):
                    route = decorator.args[0]
                    if (
                        isinstance(route, ast.Constant)
                        and isinstance(route.value, str)
                        and "{project_id}" in route.value
                    ):
                        routes.append(
                            {
                                "method": decorator.func.attr.upper(),
                                "path": route.value,
                                "line": decorator.lineno,
                            }
                        )
            has_project = bool(PROJECT_TOKEN.search(fragment))
            entities = sorted(symbols & legacy_entities)
            if not routes and not (has_project and entities):
                continue
            read = bool(routes) and all(route["method"] == "GET" for route in routes)
            # A GET label is not proof of purity: mutating legacy dashboard is
            # explicitly preserved as a risk, not executed during inspection.
            mutation = bool(
                re.search(
                    r"\b(?:commit|flush|add|delete|run_project_cycle)\s*\(", fragment
                )
            )
            canonical = relative.startswith(excluded_new) or (
                "EnterpriseWorkspace" in fragment
                or "enterprise_workspace_id" in fragment
                or "workspace" in node.name
            )
            awareness = "DUAL_CONTEXT" if canonical else "LEGACY_ONLY"
            consumers.append(
                {
                    "id": f"CON-{len(consumers) + 1:04}",
                    "path": relative,
                    "line": node.lineno,
                    "symbol": node.name,
                    "legacy_entities": entities,
                    "routes": routes,
                    "awareness": awareness,
                    "migration": disposition(
                        relative, node.name, read=read and not mutation
                    ),
                    "authority": source_authority(relative),
                    "static_write_signal": mutation,
                    "read_route": read,
                    "execution_proven": False,
                    "note": "Static lexical/AST candidate; not a runtime call-graph proof."
                    + (
                        " Legacy GET has a write/cycle signal; do not use as a harmless diagnostic."
                        if read and mutation
                        else ""
                    ),
                    "imported_legacy_entities": sorted(imported & legacy_entities),
                }
            )
    # Include all explicit legacy HTTP source references in the active frontend,
    # preserving exact line evidence without declaring unreachable views live.
    frontend: list[dict] = []
    for path in sorted((ROOT / "frontend/src").rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        source = path.read_text(encoding="utf-8-sig")
        lines = source.splitlines()
        for number, line in enumerate(lines, 1):
            if re.search(r"/projects/\$\{|[\"'`]projects/\$\{", line):
                relative = path.relative_to(ROOT).as_posix()
                frontend.append(
                    {
                        "id": f"FE-{len(frontend) + 1:04}",
                        "path": relative,
                        "line": number,
                        "awareness": "LEGACY_ONLY",
                        "migration": disposition(relative, line[:160]),
                        "authority": source_authority(relative),
                        "execution_proven": False,
                        "note": "Explicit projects HTTP route reference; runtime reachability not inferred.",
                    }
                )
    payload = {
        "inventory_kind": "POST_IMPLEMENTATION_STATIC_TRACEABILITY"
        if args.include_o1a
        else "PRE_IMPLEMENTATION_STATIC_CHARACTERIZATION",
        "canonical_identity": "enterprise_workspaces workspace_type_code=project",
        "legacy_identity": "projects.id (distinct numeric namespace)",
        "scope": "All backend/app Python FK declarations and functions directly referencing proven FK entities or project_id HTTP routes; all frontend/src explicit projects HTTP references.",
        "limitations": [
            "Static source inventory is exhaustive for the stated predicates, not transitive/runtime reachability.",
            "CANONICAL_AWARE only applies to a consumer with no legacy dependency; these rows intentionally inventory legacy dependencies.",
            "New O1A code inclusion is explicit via --include-o1a; the original baseline inventory remains separate.",
        ],
        "counts": {
            "fk_entities": len(foreign_keys),
            "backend_function_candidates": len(consumers),
            "frontend_route_references": len(frontend),
        },
        "awareness_counts": dict(
            Counter(row["awareness"] for row in foreign_keys + consumers + frontend)
        ),
        "migration_counts": dict(
            Counter(row["migration"] for row in foreign_keys + consumers + frontend)
        ),
        "foreign_keys": foreign_keys,
        "backend_consumers": consumers,
        "frontend_consumers": frontend,
        "source_snapshots": snapshots,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), **payload["counts"]}))


if __name__ == "__main__":
    main()
