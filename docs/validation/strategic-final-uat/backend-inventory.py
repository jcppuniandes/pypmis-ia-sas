"""Read-only source inventory for final strategic UAT (no application/DB imports).

Run from repository root: backend/.venv/Scripts/python.exe docs/validation/strategic-final-uat/backend-inventory.py
Generated evidence describes source presence, never test execution or business acceptance.
"""
from __future__ import annotations

import ast
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
MODULES = ROOT / "backend/app/modules"
TREES: dict[Path, ast.Module] = {}
SOURCES: dict[Path, str] = {}


def parse(path):
    path = Path(path)
    if path not in TREES:
        SOURCES[path] = path.read_text(encoding="utf-8-sig")
        TREES[path] = ast.parse(SOURCES[path])
    return TREES[path]


def rel(path):
    return str(Path(path).relative_to(ROOT)).replace("\\", "/")


def ref(path, node):
    return f"{rel(path)}:{node.lineno}"


def strings(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def dump(name, rows):
    (OUT / (name + ".json")).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if rows and isinstance(rows, list) and isinstance(rows[0], dict):
        keys = list(dict.fromkeys(k for row in rows for k in row))
        with (OUT / (name + ".csv")).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: "; ".join(map(str, v)) if isinstance(v, (list, set, tuple)) else v for k, v in row.items()})


# Evaluate only source constants and in-memory set extensions; never import app.
permission_path = MODULES / "enterprise_structure/permissions.py"
constant_env = {"frozenset": frozenset, "set": set, "tuple": tuple}
constant_errors = []
# The permission catalog is constant-only too; evaluate without app imports.
constant_source_path = MODULES / "enterprise_structure/constants.py"
for node in parse(constant_source_path).body:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For)):
        candidate = ast.Module(body=[node], type_ignores=[])
        try:
            exec(compile(ast.fix_missing_locations(candidate), str(constant_source_path), "exec"), {"__builtins__": {}, **constant_env}, constant_env)
        except Exception as exc:
            constant_errors.append({"source": ref(constant_source_path, node), "error": str(exc)})
for node in parse(permission_path).body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_PERMISSION_SEED_LOCK" for t in node.targets):
        break
    if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For)):
        continue
    candidate = ast.Module(body=[node], type_ignores=[])
    # Only frozenset/set are callable in the extracted constants.
    if any(isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in {"frozenset", "set", "tuple"}) for n in ast.walk(node)):
        continue
    try:
        exec(compile(ast.fix_missing_locations(candidate), str(permission_path), "exec"), {"__builtins__": {}, **constant_env}, constant_env)
    except Exception as exc:
        constant_errors.append({"source": ref(permission_path, node), "error": str(exc)})

role_maps = {k: v for k, v in constant_env.items() if k.endswith("_ROLE_PERMISSIONS") and isinstance(v, dict)}
role_permissions = defaultdict(set)
role_origins = defaultdict(set)
for family, mapping in role_maps.items():
    for role, permissions in mapping.items():
        role_permissions[role].update(permissions)
        role_origins[role].add(family)
# Include exact organization/configuration/auditor/viewer grants defined inside
# the bootstrap function, while never executing that function or its DB calls.
for node in ast.walk(parse(permission_path)):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "grants_by_role" for t in node.targets):
        grants = eval(compile(ast.Expression(node.value), str(permission_path), "eval"), {"__builtins__": {}, **constant_env})
        for role, permissions in grants.items():
            role_permissions[role].update(permissions)
            role_origins[role].add("grants_by_role")
dump("backend-role-permissions", [
    {"role_code": role, "permission_keys": sorted(permissions), "source_families": sorted(role_origins[role]),
     "evidence": rel(permission_path), "execution_status": "SOURCE_INSPECTED_NOT_EXECUTED"}
    for role, permissions in sorted(role_permissions.items())
])

# Find every module router included in the canonical /api/v1 router.
main_router_path = ROOT / "backend/app/api/v1/router.py"
main_tree = parse(main_router_path)
router_aliases = {}
for node in main_tree.body:
    if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app.modules."):
        for item in node.names:
            router_aliases[item.asname or item.name] = (node.module.split(".")[2], item.name)
includes = []
for node in main_tree.body:
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "include_router" and call.args:
            arg = call.args[0]
            if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id in router_aliases:
                module, router_file = router_aliases[arg.value.id]
                extra_prefix = next((k.value.value for k in call.keywords if k.arg == "prefix" and isinstance(k.value, ast.Constant)), "")
                includes.append((module, MODULES / module / (router_file + ".py"), arg.attr, extra_prefix))
# Generic configuration endpoints are part of the compatibility/security review.
includes.append(("admin_configuration", ROOT / "backend/app/api/v1/routers/admin_configuration.py", "router", ""))

frontend_files = {p: p.read_text(encoding="utf-8-sig") for p in (ROOT / "frontend/src").rglob("*") if p.suffix in {".ts", ".tsx"} and ".test." not in p.name}
frontend_routes = []
for path, source in frontend_files.items():
    constants = dict(re.findall(r'(?:const|let)\s+(\w+)\s*=\s*["\'](/api/v1[^"\']*)["\']', source))
    for match in re.finditer(r'([`"\'])([^`"\'\n]*?/[^`"\'\n]*)\1', source):
        value = match.group(2)
        for key, content in constants.items():
            value = value.replace("${" + key + "}", content)
        if value.startswith("/api/v1"):
            value = re.sub(r"\$\{[^}]+\}", "{id}", value).split("?")[0]
            frontend_routes.append((path, match.start(), value))

test_sources = {p: p.read_text(encoding="utf-8-sig") for p in (ROOT / "backend/tests").rglob("test_*.py")}
function_corpus = {}
for p in MODULES.rglob("*.py"):
    tree = parse(p)
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_corpus[(p, n.name)] = n


def permissions_for(path, function, visited=None):
    visited = set(visited or ())
    marker = (path, function.name)
    if marker in visited:
        return set(), set()
    visited.add(marker)
    permissions = set()
    guards = set()
    funcs = {n.name: n for n in parse(path).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if "authoriz" in name or "permission" in name or name in {"_service", "_require"}:
                permissions.update(s for s in strings(node) if re.match(r"^[a-z][a-z_]*(?:\.[a-z_]+)+$", s))
                guards.add(name)
            if name in funcs and name != function.name:
                child, child_guards = permissions_for(path, funcs[name], visited)
                # Helpers may dispatch several permission actions. Keep their union explicit.
                permissions.update(child)
                guards.update(child_guards)
    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "require_tenant_configurator" for n in ast.walk(function)):
        permissions.add("can_configure")
    return permissions, guards


def route_shape(value):
    return re.sub(r"\{[^}]+\}", "{}", value.rstrip("/"))


endpoints = []
module_names = set()
for module, path, router_name, include_prefix in includes:
    module_names.add(module)
    tree = parse(path)
    prefixes = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "APIRouter":
            for target in node.targets:
                if isinstance(target, ast.Name):
                    prefixes[target.id] = next((k.value.value for k in node.value.keywords if k.arg == "prefix" and isinstance(k.value, ast.Constant)), "")
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in fn.decorator_list:
            if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == router_name and decorator.func.attr in {"get", "post", "put", "patch", "delete"}):
                continue
            suffix = decorator.args[0].value
            endpoint = "/api/v1" + include_prefix + prefixes.get(router_name, "") + suffix
            permissions, guards = permissions_for(path, fn)
            is_admin = module in {"admin_configuration", "investment_evidence_policy"} or "/admin/" in endpoint or "/admin-" in endpoint or any(".admin." in p or p.startswith("admin.") for p in permissions)
            method = decorator.func.attr.upper()
            mode = "ADMIN MODE" if is_admin else "READ-ONLY SHARED CONTEXT" if method == "GET" else "USER MODE"
            consumers = sorted({rel(p) for p, _, value in frontend_routes if route_shape(value) == route_shape(endpoint)})
            direct_tests = sorted(rel(p) for p, source in test_sources.items() if endpoint.replace("/api/v1", "").split("{")[0] in source and len(endpoint.replace("/api/v1", "").split("{")[0]) > 8)
            related_tests = sorted(rel(p) for p, source in test_sources.items() if module in p.stem or f"app.modules.{module}" in source)
            endpoints.append({"endpoint": endpoint, "method": method, "module": module, "purpose": fn.name.replace("_", " "), "mode": mode,
                              "permission": sorted(permissions) or ["HELPER_OR_SERVICE_AUTHORIZATION_REQUIRES_REVIEW"], "authorization_guards": sorted(guards),
                              "live_deprecated": "LIVE_ROUTER_REGISTERED", "frontend_consumer": consumers or ["NO_DIRECT_LITERAL_MATCH_NOT_PROOF_UNUSED"],
                              "uat_coverage": "NOT_EXECUTED_BY_INVENTORY", "test_evidence_direct_family": direct_tests,
                              "test_evidence_module": related_tests, "evidence": ref(path, fn),
                              "permission_precision": "SOURCE_LITERAL_OR_TRANSITIVE_HELPER_UNION"})
    if module == "qra_engine":
        for section in ("summary", "percentiles", "convergence", "sensitivity", "milestones", "drivers", "histogram", "cdf", "provenance"):
            endpoint = f"/api/v1/qra-engine/runs/{{run_id}}/{section}"
            consumers = sorted({rel(p) for p, _, value in frontend_routes if route_shape(value) == route_shape(endpoint)})
            endpoints.append({"endpoint": endpoint, "method": "GET", "module": module, "purpose": f"run result {section}", "mode": "READ-ONLY SHARED CONTEXT",
                              "permission": ["qra_run.read"], "authorization_guards": ["_authorized"], "live_deprecated": "LIVE_DYNAMIC_ROUTER_REGISTERED",
                              "frontend_consumer": consumers or ["DYNAMIC_RESULT_SECTION_CLIENT"], "uat_coverage": "NOT_EXECUTED_BY_INVENTORY",
                              "test_evidence_direct_family": [], "test_evidence_module": sorted(rel(p) for p in test_sources if "qra_engine" in p.stem),
                              "evidence": rel(path) + ":95", "permission_precision": "EXACT_DYNAMIC_FACTORY"})
endpoints.sort(key=lambda row: (row["module"], row["endpoint"], row["method"]))
dump("backend-api-inventory", endpoints)

# Explicit classes plus shared domain models referenced by strategic code.
module_sources = {p: SOURCES.get(p) or p.read_text(encoding="utf-8-sig") for p in MODULES.rglob("*.py")}
identifier_consumers = defaultdict(set)
for source_path, source in module_sources.items():
    for identifier in set(re.findall(r"\b[A-Za-z_][A-Za-z_0-9]*\b", source)):
        identifier_consumers[identifier].add(source_path)
tables = []
model_paths = list(MODULES.rglob("models.py")) + [ROOT / "backend/app/domain/models.py"]
for path in model_paths:
    for cls in parse(path).body:
        if not isinstance(cls, ast.ClassDef):
            continue
        table = next((n.value.value for n in cls.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in n.targets) and isinstance(n.value, ast.Constant)), None)
        if not table:
            continue
        refs = sorted(rel(p) for p in identifier_consumers[cls.name] if p != path)
        if path.parent.name == "domain" and not refs:
            continue
        if any(s in table for s in ("receipt", "idempotency", "command", "recent_workspace")):
            category = "TRANSIENT/COMMAND_RECEIPT"
        elif any(s in table for s in ("history", "revision", "snapshot", "audit", "security_event", "authorization_output", "decision_vote", "run_review", "run_result", "versions", "core_releases")):
            category = "HISTORICAL_REQUIRED"
        elif any(s in table for s in ("configuration", "number_sequence", "role", "permission", "module_setting", "taxonomy", "framework", "criterion", "criteria", "access_assignment", "group_member")):
            category = "CONFIGURATION"
        elif refs or path.parent.name != "domain":
            category = "ACTIVE"
        else:
            category = "POTENTIALLY_ORPHAN"
        fks = sorted({n.args[0].value for n in ast.walk(cls) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "ForeignKey" and n.args and isinstance(n.args[0], ast.Constant)})
        tables.append({"table": table, "model": cls.name, "classification": category, "scope": "STRATEGIC_MODULE" if "modules" in path.parts else "SHARED_REFERENCED_OR_OPERATIONAL_COMPATIBILITY",
                       "evidence": ref(path, cls), "foreign_keys": fks, "source_consumers": refs,
                       "usage_evidence": "DECLARED_MODEL_AND_SOURCE_REFERENCES_NOT_ROW_COUNTS", "drop_authorized": False,
                       "retention_note": "Operational/source references and immutable historical rows must remain; receipt expiry is not deletion approval."})
tables.sort(key=lambda row: row["table"])
dump("backend-database-inventory", tables)

coverage = []
for module in sorted(module_names):
    rows = [r for r in endpoints if r["module"] == module]
    tests = sorted({t for r in rows for t in r["test_evidence_module"]})
    shared_config = {"project_creation": "enterprise_structure/project_configuration.py", "project_workspace_initialization": "enterprise_structure/project_configuration.py", "physical_workspace_creation": "enterprise_structure/physical_configuration.py", "physical_workspace_initialization": "enterprise_structure/physical_configuration.py", "qra_engine": "qra_foundation/policy.py + qra_foundation/router.py", "workspace_context": "enterprise_structure + admin_configuration Workspace Type/module/navigation configuration"}
    coverage.append({"module": module, "registered_endpoints": len(rows), "admin_endpoints": sum(r["mode"] == "ADMIN MODE" for r in rows),
                     "shared_read_endpoints": sum(r["mode"] == "READ-ONLY SHARED CONTEXT" for r in rows), "user_write_endpoints": sum(r["mode"] == "USER MODE" for r in rows),
                     "test_files": tests, "current_uat_status": "NOT_EXECUTED_BY_INVENTORY", "admin_prerequisite": "DEDICATED_SOURCE_ENDPOINTS_PRESENT" if any(r["mode"] == "ADMIN MODE" for r in rows) else shared_config.get(module, "SHARED_CONFIGURATION_OR_INTENTIONAL_FIXED_BEHAVIOR_REVIEW_REQUIRED")})
dump("backend-module-coverage", coverage)
dump("backend-inventory-summary", {"inventory_kind": "STATIC_SOURCE_READ_ONLY", "endpoints": len(endpoints), "modules": len(module_names), "tables": len(tables),
     "mode_counts": dict(Counter(r["mode"] for r in endpoints)), "table_classification_counts": dict(Counter(t["classification"] for t in tables)),
     "role_codes": len(role_permissions), "role_permission_pairs": sum(map(len, role_permissions.values())), "constant_extraction_errors": constant_errors,
     "limitations": ["Permission extraction may union action-dispatch helper permissions; not a substitute for HTTP denial tests.",
                     "GET is classified shared-read by API semantics; consumer mode and business side effects require separate audit.",
                     "Frontend consumers use direct/static-template matching; no match is not proof of dead code.",
                     "Test-file presence is evidence inventory, never PASS. No DB connection or live app imported.",
                     "Database classification is source-based retention guidance, not proof of physical rows, deployment usage, or orphanhood."]})
print(json.dumps({"endpoints": len(endpoints), "modules": len(module_names), "tables": len(tables), "roles": len(role_permissions), "constant_extraction_errors": constant_errors}, indent=2))
