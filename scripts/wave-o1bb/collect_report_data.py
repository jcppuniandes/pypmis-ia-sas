"""Collect final executed evidence, never infer runtime PASS from source presence."""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bb-20261020"
DOCS = ROOT / "docs/validation/wave-o1bb-20261020"
PROMPT = Path("C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1B_B_SCHEDULE_FOUNDATION_WBS_ACTIVITIES_VERSIONS_P6_GOVERNANCE.md")


def read(path, default=None):
    return json.loads(path.read_text("utf-8")) if path.is_file() else default


def cases(path):
    if not path.is_file():
        return []
    return [
        {"name": node.get("name"), "class": node.get("classname"), "seconds": float(node.get("time", 0)),
         "result": "FAIL" if node.find("failure") is not None or node.find("error") is not None else "SKIP" if node.find("skipped") is not None else "PASS",
         "evidence": str(path.relative_to(QA) if path.is_relative_to(QA) else path.relative_to(ROOT)).replace("\\", "/")}
        for node in ET.parse(path).iter("testcase")
    ]


def main():
    backend = cases(QA / "backend-postgres.xml") + cases(QA / "exchange-docker.xml")
    regression = cases(QA / "regression-final.xml")
    frontend_path = QA / "frontend-final.xml"
    if not frontend_path.exists():
        frontend_path = ROOT / "outputs/.qa/wave-o1bb-20261021/frontend-final.xml"
    frontend = cases(frontend_path)
    browser = read(QA / "chromium/browser-uat.json", {"result": "PENDING", "checks": []})
    before = read(DOCS / "preservation-before.json")
    after = read(DOCS / "preservation-after.json")
    preserved = bool(after and before and all(before["observation"][key] == after["observation"][key] for key in ("canonical_id14_row_sha256", "project14_row_sha256", "project14_references")))
    migration = read(QA / "migration-roundtrip.json")
    backend_pass = bool(backend and all(row["result"] == "PASS" for row in backend) and migration)
    regression_pass = len(regression) == 306 and all(row["result"] == "PASS" for row in regression)
    frontend_checks = read(QA / "frontend-checks.json", {})
    frontend_pass = bool(frontend and all(row["result"] == "PASS" for row in frontend)
                         and frontend_checks.get("checks")
                         and all(row.get("result") == "PASS" and row.get("exit_code") == 0 for row in frontend_checks["checks"]))
    runtime_pass = backend_pass and regression_pass and frontend_pass and browser.get("result") == "PASS" and preserved
    gates_text = PROMPT.read_text("utf-8").split("# 49. RELEASE CRITERIA")[1].split("# 50.")[0]
    criteria = [line.split(" = PASS")[0].strip() for line in gates_text.splitlines() if " = PASS" in line]
    gates = [[f"RC-{i:02}", label, "PASS" if runtime_pass else "PENDING", "PostgreSQL suites; Chromium UAT; preservation; release-manifest.json"] for i, label in enumerate(criteria, 1)]
    requirements = [[int(number), title.title(), "PASS" if runtime_pass else "PENDING", "Pruebas ejecutadas y criterios de liberación en hojas temáticas"] for number, title in re.findall(r"^#{1,2} (\d+)\. (.+)$", PROMPT.read_text("utf-8"), re.MULTILINE)]
    perf = read(QA / "exchange-performance.json", {})
    performance = [[label, perf[key]["sample_count"], perf[key]["minimum_ms"], perf[key]["median_ms"], perf[key]["maximum_ms"]] for label, key in (("Parseo XML", "xml_parse"), ("Parseo XER", "xer_parse"), ("Diff", "snapshot_diff")) if key in perf]
    performance += [[row["label"], 1, row["elapsed_ms"], row["elapsed_ms"], row["elapsed_ms"]] for row in browser.get("observations", [])]
    api = read(DOCS / "api-inventory.json", [])
    if isinstance(api, dict):
        api = api.get("routes", api.get("items", []))
    if api and isinstance(api[0], dict):
        api = [[row.get("method", ",".join(row.get("methods", []))), row["path"], row.get("name", row.get("operation", "")), row.get("permission", ", ".join(row.get("permissions", [])) or row.get("duty", "Schedule scoped permission"))] for row in api]
    data = {
        "issue_date": "21 octubre 2026", "baseline_head": before["baseline_head"],
        "release_validated": runtime_pass,
        "release_state": "WAVE_O1B_B_SCHEDULE_FOUNDATION_RELEASE_VALIDATED" if runtime_pass else "WAVE_O1B_B_SCHEDULE_FOUNDATION_RELEASE_PENDING",
        "release_explanation": "Los controles técnicos requeridos pasan en el entorno aislado. No incluye despliegue de la base habitual ni aceptación de negocio." if runtime_pass else "Los controles pendientes o fallidos impiden declarar la liberación validada.",
        "final_output": "READY_FOR_WAVE_O1B_C_COST_FOUNDATION" if runtime_pass else "NOT_READY_FOR_WAVE_O1B_C_COST_FOUNDATION",
        "backend_result": "PASS" if backend_pass else "PENDING_OR_FAIL", "backend_count": len(backend),
        "regression_result": "PASS" if regression_pass else "PENDING_OR_FAIL", "regression_count": len(regression),
        "preservation_result": "PASS" if preserved else "PENDING", "cases": backend, "regression": regression,
        "frontend": frontend, "browser": browser, "api": api, "requirements": requirements,
        "release_criteria": gates, "performance": performance, "migration": migration,
        "defects": [
            ["D-01", "S2", "Dos candidatos rebaseline sobre la misma ScheduleVersion podían usar un predecesor obsoleto", "RESOLVED", "Comprobar identidad del último baseline aprobado bajo bloqueo del registro; prueba de carrera lógica"],
            ["D-02", "S2", "Snapshots manuales malformados podían causar error no controlado", "RESOLVED", "Validación estructural y numérica antes de acceder a campos; pruebas de tipos y límites"],
            ["D-03", "S2", "Mapeos heredados de un objeto cambiado requerían revisión explícita", "RESOLVED", "REQUIRES_REVIEW o BROKEN conserva el historial y bloquea promoción"],
            ["D-04", "TEST", "Arranque inicial de pytest simultáneo al provisionamiento produjo colisión DDL", "RESOLVED", "Secuencia provisionar y luego probar; ejecución interrumpida no contada como validación"],
            ["D-05", "S2", "Tipo de actividad nulo y lag booleano podían causar error en Health", "RESOLVED", "Validación explícita del tipo de actividad y rechazo global de booleanos numéricos; pruebas de regresión"],
            ["L-01", "LIMIT", "Sin export XER ni transporte nativo BaselineProject", "DECLARED", "XML y manifiesto del subconjunto permitido; no prometer paridad P6"],
            ["L-02", "LIMIT", "Sin ejecución del archivo exportado dentro de Primavera ni XSD de instalación", "DECLARED", "Parser loop real separado de certificación de compatibilidad Primavera"],
            ["L-03", "LIMIT", "Escala productiva y despliegue sobre base habitual no ejecutados", "PENDING_SCOPE", "Observaciones pequeñas locales no representan SLA"],
            ["L-04", "BUSINESS", "Aceptación de representantes de negocio sin firmas", "PENDING", "No se inventa aceptación humana"],
        ],
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "package-data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    relevant = [name for name in files if not name.startswith("outputs/") and not name.endswith("release-manifest.json") and ("schedule_foundation" in name or "schedule-foundation" in name or "wave-o1bb" in name or name in {"backend/app/api/v1/router.py", "backend/alembic/env.py", "frontend/src/components/AdminConfigurationView.tsx", "frontend/src/features/workspace-context/WorkspaceOperationalPage.tsx", "frontend/src/navigation/applicationNavigation.ts"})]
    frozen = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in relevant if (ROOT / name).is_file() and name != "docs/validation/wave-o1bb-20261020/source-manifest.json"}
    (DOCS / "source-manifest.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print(json.dumps({key: data[key] for key in ("release_state", "backend_count", "backend_result", "regression_count", "regression_result", "preservation_result")}))


if __name__ == "__main__":
    main()
