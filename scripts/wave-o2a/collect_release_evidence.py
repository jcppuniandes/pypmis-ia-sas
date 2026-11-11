"""Collect O2A technical release evidence; missing or stale evidence never passes."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2a-20261109"
PRESERVATION = ROOT / "docs/validation/wave-o2a-20261109"
BASELINE = "3889d717c4f86b1f3453927d09adc990d592a958"
RELEASE = "WAVE_O2A_ENGINEERING_FOUNDATION_RELEASE_VALIDATED"
NEXT = "READY_FOR_WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION"
MIGRATION = "backend/alembic/versions/20261109_0076_engineering_foundation.py"
PROTECTED = (
    "backend/alembic/versions",
    "backend/app/domain/models.py",
    "backend/app/domain/schemas.py",
    "frontend/src/App.tsx",
    "frontend/src/components/BimIfcModelViewer.tsx",
)
FRONTEND_PATHS = (
    "frontend/src",
    "frontend/e2e/engineering-foundation.spec.ts",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/eslint.config.js",
    "frontend/playwright.config.ts",
    "frontend/vitest.setup.ts",
)
BROWSER_CHECKS = {
    "ADMIN_PROFILE_DRAFT_CREATED_WITH_CONTROLLED_CATALOGS",
    "ADMIN_INDEPENDENT_PUBLISH_IMMUTABLE",
    "REGISTER_AND_REVISION_REAL_UI",
    "CDE_ATTACHMENT_PINNED_BY_REAL_HASH",
    "SCOPE_PLAN_EWP_MAPPINGS_REAL_UI",
    "TWO_ROUNDS_COMMENT_RESPONSE_CLOSE_AND_INDEPENDENT_CHECK_APPROVAL",
    "IFC_EXPLICIT_SEPARATE_ACTOR_AND_RELEASE_HASH",
    "GOVERNED_ENGINEERING_EVIDENCE_CONSUMED_BY_AWP_NO_PACKAGE_RELEASE",
    "APPROVED_REVISION_IMMUTABLE_AND_READS_DO_NOT_MUTATE_HISTORY",
}
PERFORMANCE_OPERATIONS = {
    "Deliverable Register",
    "Revision history",
    "Review queue (status projection)",
    "IFC release queue (status projection)",
    "EWP mapping",
    "Engineering Readiness",
    "Engineering Look-Ahead",
}
POSTGRES_REQUIRED_CASES = {
    "test_engineering_migration_single_head_and_postgresql_roundtrip",
    "test_deliverable_identity_catalog_pagination_etag_and_idempotency",
    "test_cde_link_for_construction_and_upload_are_not_approval_or_release",
    "test_review_comments_response_revise_resubmit_check_and_approval",
    "test_rejection_is_explicit_and_requires_successor",
    "test_ifc_release_is_independent_immutable_and_successor_is_effective_by_cutoff",
    "test_mapping_is_many_to_many_typed_append_only_and_project_scoped",
    "test_awp_assesses_ifc_evidence_without_auto_clear_or_package_release",
    "test_schedule_successor_stales_mapping_without_remapping",
    "test_persisted_engineering_readiness_expiry_supersession_and_integrity",
    "test_engineering_release_is_only_explicit_milestone_evidence",
    "test_engineering_issue_date_is_explicit_forecast_input_and_approval_stays_frozen",
}


def relative(path):
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, encoding="utf-8", errors="replace"
    )


def frontend_hashes():
    names = git(
        "ls-files", "-z", "-co", "--exclude-standard", "--", *FRONTEND_PATHS
    ).split("\0")
    return {
        name: sha256(ROOT / name)
        for name in sorted(set(names))
        if (ROOT / name).is_file()
    }


def backend_source():
    sys.path.insert(0, str(ROOT / "backend"))
    from tests.run_o1bd_validation import source_hashes
    from tests.run_o2a_validation import CASES

    return source_hashes(), CASES


def gate(**details):
    return {
        "status": "PENDING",
        "evidence": [],
        "artifact_sha256": {},
        "errors": [],
        **details,
    }


def add_evidence(path, report):
    name = relative(path)
    report["evidence"].append(name)
    if path.is_file():
        report["artifact_sha256"][name] = sha256(path)


def read_json(path, report, *, required=True):
    if not path.is_file():
        if required:
            report["errors"].append(f"Falta {relative(path)}")
        return None
    add_evidence(path, report)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise TypeError("se esperaba un objeto JSON")
        return value
    except (TypeError, ValueError, OSError) as exc:
        report["errors"].append(f"{relative(path)}: {exc}")
        report["status"] = "FAIL"
        return None


def verify_sources(proof, current, report):
    frozen = proof.get("source_sha256") if proof else None
    if not isinstance(frozen, dict) or not frozen:
        report["errors"].append("No hay inventario SHA-256 de las fuentes ejecutadas")
        return {"status": "PENDING", "checked_files": 0, "changed_files": []}
    changed = sorted(
        name
        for name in frozen.keys() | current.keys()
        if frozen.get(name) != current.get(name)
    )
    unchanged = proof.get("source_unchanged_during_validation") is True
    if not unchanged:
        report["errors"].append(
            "La ejecución no demuestra que las fuentes permanecieran intactas"
        )
    if changed:
        report["errors"].append(
            f"Inventario SHA-256 distinto del ejecutado: {len(changed)} archivo(s)"
        )
    return {
        "status": "PASS" if unchanged and not changed else "STALE",
        "checked_files": len(current),
        "changed_files": changed,
    }


def matches_postgres_run(path, proof):
    if proof.get("junit_sha256"):
        return proof["junit_sha256"] == sha256(path)
    try:
        start, end = (
            datetime.fromisoformat(proof[key]) for key in ("started_at", "completed_at")
        )
        return start <= datetime.fromtimestamp(path.stat().st_mtime, UTC) <= end
    except (KeyError, TypeError, ValueError, OSError):
        return False


def postgres(qa, current, expected_modules):
    result = gate(
        counts={"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0},
        cases=[],
        suites={},
    )
    path = qa / "final-postgres-junit.xml"
    proof = read_json(qa / "postgres-source-proof.json", result)
    result["source_freshness"] = verify_sources(proof, current, result)
    result["pytest_exit_code"] = (proof or {}).get("pytest_exit_code")
    for name in ("started_at", "completed_at", "changed_during_validation"):
        result[name] = (proof or {}).get(name)
    if not path.is_file():
        result["errors"].append(f"Falta {relative(path)}")
        if result["pytest_exit_code"] not in (None, 0):
            result["status"] = "FAIL"
        return result
    add_evidence(path, result)
    try:
        tree = ET.parse(path).getroot()
        tally = Counter()
        seen = set()
        for node in tree.iter("testcase"):
            name, module = node.attrib["name"], node.attrib["classname"]
            seconds = float(node.get("time", "0"))
            state, problem = "PASS", None
            for tag, state_value in (
                ("error", "ERROR"),
                ("failure", "FAIL"),
                ("skipped", "SKIP"),
            ):
                problem = node.find(tag)
                if problem is not None:
                    state = state_value
                    break
            row = {"name": name, "class": module, "seconds": seconds, "result": state}
            if problem is not None:
                row["message"] = (problem.get("message") or "").strip()[:1000]
                row["detail"] = (problem.text or "").strip()[:4000]
            result["cases"].append(row)
            tally[state] += 1
            result["suites"].setdefault(module, Counter())[state] += 1
            if state == "PASS":
                seen.add(name.split("[", 1)[0])
        result["counts"] = {
            "total": sum(tally.values()),
            "passed": tally["PASS"],
            "failed": tally["FAIL"],
            "errors": tally["ERROR"],
            "skipped": tally["SKIP"],
        }
        suite_nodes = [tree] if tree.tag == "testsuite" else tree.findall("./testsuite")
        for xml_key, summary_key in (
            ("tests", "total"),
            ("failures", "failed"),
            ("errors", "errors"),
            ("skipped", "skipped"),
        ):
            declared = sum(int(node.get(xml_key, "0")) for node in suite_nodes)
            if declared != result["counts"][summary_key]:
                raise ValueError(f"JUnit inconsistente: {xml_key}={declared}")
        executed_modules = {
            module.rsplit(".", 1)[-1] + ".py" for module in result["suites"]
        }
        result["missing_modules"] = sorted(set(expected_modules) - executed_modules)
        result["missing_required_cases"] = sorted(POSTGRES_REQUIRED_CASES - seen)
    except (ET.ParseError, KeyError, ValueError, OSError) as exc:
        result["errors"].append(f"JUnit inválido: {exc}")
        result["status"] = "FAIL"
        return result
    if tally["FAIL"] or tally["ERROR"] or tally["SKIP"]:
        result["errors"].append("JUnit contiene fallas, errores o casos omitidos")
    if result["missing_modules"] or result["missing_required_cases"]:
        result["errors"].append("Faltan suites o casos obligatorios aprobados")
    if proof and not matches_postgres_run(path, proof):
        result["errors"].append("El JUnit no corresponde a la ejecución registrada")
    if result["source_freshness"]["status"] == "STALE":
        result["status"] = "STALE"
    elif result["pytest_exit_code"] not in (None, 0) or any(
        tally[state] for state in ("FAIL", "ERROR", "SKIP")
    ):
        result["status"] = "FAIL"
    elif (
        proof
        and result["pytest_exit_code"] == 0
        and result["source_freshness"]["status"] == "PASS"
    ):
        result["status"] = "PASS" if tally["PASS"] and not result["errors"] else "FAIL"
    return result


def latest_browser_run(chromium):
    candidates = list(chromium.rglob("browser-uat.json"))
    return (
        max(
            candidates, key=lambda path: (path.stat().st_mtime_ns, path.as_posix())
        ).parent
        if candidates
        else chromium
    )


def browser(chromium, current):
    run = latest_browser_run(chromium)
    uat, perf = (
        gate(checks=[], observations={}, mutations=[], browser_errors=[]),
        gate(operations=[]),
    )
    browser_path, perf_path = run / "browser-uat.json", run / "performance.json"
    observed = read_json(browser_path, uat)
    measured = read_json(perf_path, perf)
    proof = read_json(run / "browser-source-proof.json", uat)
    uat["source_freshness"] = verify_sources(proof, current, uat)
    uat["playwright_exit_code"] = (proof or {}).get("playwright_exit_code")
    if observed is not None:
        for key in (
            "result",
            "stage",
            "project_workspace_id",
            "as_of_utc",
            "checks",
            "observations",
            "mutations",
            "browser_errors",
        ):
            if key in observed:
                uat[key] = observed[key]
        checks = observed.get("checks")
        validated_checks = {
            check.get("code")
            for check in (checks if isinstance(checks, list) else [])
            if isinstance(check, dict) and check.get("result") == "PASS"
        }
        uat["missing_checks"] = sorted(BROWSER_CHECKS - validated_checks)
        browser_valid = (
            observed.get("result") == "PASS"
            and observed.get("browser_errors") == []
            and isinstance(checks, list)
            and not uat["missing_checks"]
            and len(validated_checks) == len(checks)
        )
        if not browser_valid:
            uat["errors"].append(
                f"Chromium no acreditó el recorrido completo: {observed.get('stage')}"
            )
            uat["status"] = "FAIL"
        elif proof:
            bound = proof.get("browser_uat_sha256") == sha256(browser_path)
            if (
                proof.get("result") != "PASS"
                or uat["playwright_exit_code"] != 0
                or not bound
            ):
                uat["errors"].append(
                    "Salida Playwright no aprobada o JSON no coincide con la ejecución"
                )
                uat["status"] = "FAIL"
            elif uat["source_freshness"]["status"] == "PASS":
                uat["status"] = "PASS"
        if uat["source_freshness"]["status"] == "STALE" and browser_valid:
            uat["status"] = "STALE"
    if measured is not None:
        for key in ("result", "scope", "register_size", "operations"):
            if key in measured:
                perf[key] = measured[key]
        operations = perf["operations"]
        names = set()
        if isinstance(operations, list):
            for item in operations:
                samples = item.get("samples_ms") if isinstance(item, dict) else None
                if (
                    isinstance(samples, list)
                    and len(samples) == 3
                    and all(type(sample) is int and sample >= 0 for sample in samples)
                    and item.get("median_ms") == sorted(samples)[1]
                    and isinstance(item.get("operation"), str)
                    and isinstance(item.get("route"), str)
                ):
                    names.add(item["operation"])
        valid = (
            measured.get("result") == "MEASURED"
            and type(perf.get("register_size")) is int
            and perf["register_size"] > 20
            and isinstance(operations, list)
            and len(names) == len(operations)
            and names == PERFORMANCE_OPERATIONS
        )
        if not valid:
            perf["errors"].append(
                "Medición incompleta: siete operaciones, tres muestras y registro >20 requeridos"
            )
            perf["status"] = (
                "FAIL" if measured.get("result") == "MEASURED" else "PENDING"
            )
        elif proof and proof.get("performance_sha256") != sha256(perf_path):
            perf["errors"].append("Mediciones no coinciden con la ejecución Playwright")
            perf["status"] = "FAIL"
        elif uat["status"] == "PASS":
            perf["status"] = "PASS"
        else:
            perf["status"] = uat["status"]
            perf["errors"].append(
                "La medición requiere la misma ejecución Chromium verificada"
            )
    return {"run_directory": relative(run), "uat": uat, "performance": perf}


def preservation(directory):
    result = gate(canonical_sha256=None, comparisons={})
    before, after = (
        read_json(directory / f"preservation-{phase}.json", result)
        for phase in ("before", "after")
    )
    if before is None or after is None:
        return result
    keys = ("canonical_id14_row_sha256", "project14_row_sha256", "project14_references")
    old, new = (observation.get("observation") for observation in (before, after))
    if not isinstance(old, dict) or not isinstance(new, dict):
        result["errors"].append("Observación de preservación inválida")
        result["status"] = "FAIL"
        return result
    for key in keys:
        result["comparisons"][key] = key in old and key in new and old[key] == new[key]
    digest = old.get(keys[0])
    result["canonical_sha256"] = digest if result["comparisons"][keys[0]] else None
    result["observed_before_at"] = before.get("observed_at_utc")
    result["observed_after_at"] = after.get("observed_at_utc")
    try:
        before_time, after_time = (
            datetime.fromisoformat(result[f"observed_{phase}_at"])
            for phase in ("before", "after")
        )
        chronological = before_time < after_time
    except (TypeError, ValueError):
        chronological = False
    if before.get("baseline_head") != BASELINE:
        result["errors"].append(
            "La captura inicial no corresponde a la revisión base autorizada"
        )
    if (
        not chronological
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        result["errors"].append(
            "Captura incompleta: tiempo o hash canónico de Project 14 inválido"
        )
    if not all(result["comparisons"].values()):
        result["errors"].append(
            "Las filas canónicas o las referencias de Project 14 no coinciden"
        )
    closeout = read_json(directory / "preservation-closeout.json", result)
    if closeout is not None:
        final = closeout.get("observation", {})
        result["observed_closeout_at"] = closeout.get("observed_at_utc")
        result["closeout_comparisons"] = {
            key: key in final and final[key] == old[key] for key in keys
        }
        if not all(result["closeout_comparisons"].values()):
            result["errors"].append(
                "La captura final de Project 14 cambió respecto a la original"
            )
    result["status"] = "FAIL" if result["errors"] else "PASS"
    return result


def protected_diff():
    result = gate(baseline=BASELINE, paths=list(PROTECTED), changes=[], violations=[])
    try:
        tokens = (
            git(
                "diff",
                "--name-status",
                "-z",
                "--no-renames",
                BASELINE,
                "--",
                *PROTECTED,
            )
            .rstrip("\0")
            .split("\0")
        )
        result["changes"] = [
            {"kind": state, "path": name}
            for state, name in zip(tokens[::2], tokens[1::2], strict=bool(tokens[0]))
        ]
        untracked = git(
            "ls-files", "-z", "--others", "--exclude-standard", "--", *PROTECTED
        ).split("\0")
        result["changes"].extend(
            {"kind": "?", "path": name} for name in untracked if name
        )
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        result["errors"].append(f"No se pudo comparar Git: {exc}")
        return result
    result["violations"] = [
        row
        for row in result["changes"]
        if (row["path"], row["kind"]) not in {(MIGRATION, "?"), (MIGRATION, "A")}
    ]
    if result["violations"]:
        result["errors"].append(
            "Archivos protegidos o migraciones históricas cambiaron"
        )
        result["status"] = "FAIL"
    elif not (ROOT / MIGRATION).is_file() or not any(
        row["path"] == MIGRATION for row in result["changes"]
    ):
        result["errors"].append("No se encontró la migración O2A como sucesora aditiva")
    else:
        result["status"] = "PASS"
    return result


def frontend(qa, current):
    result = gate(checks=[])
    proof = read_json(qa / "frontend-validation.json", result)
    result["source_freshness"] = verify_sources(proof, current, result)
    if proof is None:
        for path in sorted(qa.glob("frontend-*.log")):
            add_evidence(path, result)
            match = re.search(
                r"^Exit code:\s*(\d+)\s*$",
                path.read_text(encoding="utf-8-sig", errors="replace"),
                re.MULTILINE,
            )
            if match:
                result["checks"].append(
                    {"log": path.name, "exit_code": int(match.group(1))}
                )
        if any(row["exit_code"] for row in result["checks"]):
            result["status"] = "FAIL"
        return result
    checks = proof.get("checks")
    result["checks"] = checks if isinstance(checks, list) else []
    names = []
    for row in result["checks"]:
        if (
            not isinstance(row, dict)
            or type(row.get("exit_code")) is not int
            or not isinstance(row.get("name"), str)
        ):
            result["errors"].append("Comprobación frontend inválida")
            continue
        names.append(row["name"])
        if row["exit_code"] != 0:
            result["errors"].append(
                f"Frontend: {row['name']} retornó {row['exit_code']}"
            )
        log = row.get("log")
        if isinstance(log, str) and Path(log).name == log and (qa / log).is_file():
            add_evidence(qa / log, result)
        else:
            result["errors"].append(f"Falta el registro frontend de {row['name']}")
    for pattern in ("vitest", "eslint", "typescript|tsc", "prettier"):
        if not any(re.search(pattern, name, re.IGNORECASE) for name in names):
            result["errors"].append(f"Falta la comprobación frontend {pattern}")
    if result["source_freshness"]["status"] == "STALE":
        result["status"] = "STALE"
    elif proof.get("result") == "PASS" and not result["errors"]:
        result["status"] = "PASS"
    elif (
        proof.get("result") == "FAIL" or result["source_freshness"]["status"] == "PASS"
    ):
        result["status"] = "FAIL"
    return result


def open_defects(qa):
    result = gate(open_s1=None, open_s2=None, defects=[])
    register = read_json(qa / "defect-register.json", result)
    if register is None:
        return result
    rows = register.get("defects")
    if (
        register.get("reviewed") is not True
        or not isinstance(rows, list)
        or not all(
            isinstance(row, dict)
            and isinstance(row.get("id"), str)
            and row.get("severity") in {"S1", "S2", "S3", "S4"}
            and row.get("status") in {"OPEN", "CLOSED"}
            for row in rows
        )
    ):
        result["errors"].append(
            "Registro de defectos incompleto o sin revisión explícita"
        )
        return result
    result["defects"] = rows
    for severity in ("S1", "S2"):
        result[f"open_{severity.lower()}"] = sum(
            row["status"] == "OPEN" and row["severity"] == severity for row in rows
        )
    result["status"] = "FAIL" if result["open_s1"] or result["open_s2"] else "PASS"
    if result["status"] == "FAIL":
        result["errors"].append("Defectos S1/S2 abiertos")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-dir", type=Path, default=QA)
    parser.add_argument("--preservation-dir", type=Path, default=PRESERVATION)
    parser.add_argument("--chromium-dir", type=Path)
    parser.add_argument("--snapshot-source", choices=("backend", "frontend", "browser"))
    parser.add_argument("--require-release", action="store_true")
    args = parser.parse_args()
    current_frontend = frontend_hashes() if args.snapshot_source != "backend" else {}
    current_backend, modules = (
        backend_source() if args.snapshot_source != "frontend" else ({}, ())
    )
    current_browser = current_backend | current_frontend
    if args.snapshot_source:
        print(
            json.dumps(
                {
                    "frontend": current_frontend,
                    "backend": current_backend,
                    "browser": current_browser,
                }[args.snapshot_source]
            )
        )
        return
    qa = args.qa_dir
    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "baseline_head": BASELINE,
        "postgresql": postgres(qa, current_backend, modules),
        "browser": browser(args.chromium_dir or qa / "chromium", current_browser),
        "preservation": preservation(args.preservation_dir),
        "protected_diff": protected_diff(),
        "frontend": frontend(qa, current_frontend),
        "open_defects": open_defects(qa),
    }
    gates = {
        **{
            name: result[name]
            for name in (
                "postgresql",
                "preservation",
                "protected_diff",
                "frontend",
                "open_defects",
            )
        },
        "chromium_uat": result["browser"]["uat"],
        "performance": result["browser"]["performance"],
    }
    result["gate_status"] = {name: proof["status"] for name, proof in gates.items()}
    result["source_freshness"] = {
        name: gates[name]["source_freshness"]
        for name in ("postgresql", "frontend", "chromium_uat")
    }
    passed = all(status == "PASS" for status in result["gate_status"].values())
    result["release_status"] = "VALIDATED" if passed else "NOT_VALIDATED"
    result["release_marker"] = RELEASE if passed else None
    result["next_increment"] = NEXT if passed else None
    qa.mkdir(parents=True, exist_ok=True)
    target = qa / "release-evidence.json"
    target.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "evidence": relative(target),
                "release_status": result["release_status"],
                "gates": result["gate_status"],
            }
        )
    )
    if args.require_release and not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
