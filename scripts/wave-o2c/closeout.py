"""Assemble release evidence without treating missing or failed tests as success."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2c-20261118"
JUNIT = {
    "Políticas y navegación": "unit-attempt-a/junit.xml",
    "Schedule PostgreSQL": "schedule-attempt-a/junit.xml",
    "API Contrato y Cost": "core-attempt-a/junit.xml",
    "API Comercial": "commercial-junit.xml",
    "Umbrales de aprobación": "commercial-policy-junit.xml",
    "Seguridad temporal": "security-final-junit.xml",
    "Fronteras HTTP": "boundary-junit.xml",
    "Chromium": "browser-attempt-b-junit.xml",
}


def read(name):
    path = QA / name
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def main():
    missing = []
    counts = {}
    for name, filename in JUNIT.items():
        path = QA / filename
        cases = list(ElementTree.parse(path).iter("testcase")) if path.exists() else []
        failed = [case for case in cases if any(case.find(key) is not None for key in ("failure", "error", "skipped"))]
        counts[name] = {"tests": len(cases), "unsuccessful": len(failed)}
        if not cases or failed:
            missing.append(name)
    commands = [
        [sys.executable, "-m", "ruff", "check", "app", "tests", "--output-format", "concise"],
        [sys.executable, "-m", "ruff", "format", "--check", "app", "tests"],
    ]
    lint = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT / "backend", capture_output=True, text=True)
        lint.append({"command": command[3:], "exit_code": result.returncode, "output": result.stdout + result.stderr})
        if result.returncode:
            missing.append("Ruff")
    (QA / "backend-checks.json").write_text(json.dumps(lint, indent=2), encoding="utf-8")
    if read("migration/proof.json").get("result") != "PASS":
        missing.append("Migración")
    if read("commercial-evidence.json").get("result") != "PASS":
        missing.append("Cadena comercial")
    if read("chromium-attempt-b/o2c-browser-evidence.json").get("result") != "PASS":
        missing.append("Escenario Chromium")
    before, after = read("project-14/preservation-before.json"), read("project-14/preservation-after.json")
    if not before or not after or before.get("observation") != after.get("observation"):
        missing.append("Proyecto 14")
    metrics = read("performance-final.json")
    if not len(metrics) >= 8 or any(len(item["ms"]) != 3 or item["response_bytes"] <= 0 for item in metrics.values()):
        missing.append("Rendimiento")
    frontend = read("frontend-checks.json")
    required = {"Vitest Contracts and Cost", "TypeScript compilation", "Production bundle", "Targeted ESLint"}
    checked = {item.get("name"): item for item in frontend.get("checks", [])}
    if not required <= checked.keys() or any(checked[name].get("exit_code") != 0 for name in required):
        missing.append("Frontend")
    passed = not missing
    marker = "WAVE_O2C_CONTRACTS_COMMITMENTS_FOUNDATION_RELEASE_VALIDATED"
    status = marker if passed else "IMPLEMENTADO CON VALIDACIÓN PENDIENTE"
    defects = [
        ["O2C-S2-01 CLOSED", "Cambio con vigencia futura", "Rechazado sin sustituir versión vigente; pruebas API y seguridad aprobadas"],
        ["O2C-S3-01 OPEN", "Latencia local del contexto", "Timeout de UAT bajo carga; recorrido final pasó con espera de carga de 180 s. Sin SLA"],
        ["O2C-S3-02 OPEN", "Hardening SQL de referencias padre", "Scope validado por API; FKs simples en parte del modelo. Acceso SQL debe ser restringido"],
        ["O2C-LIM-01", "Cost REFERENCE_ONLY", "Referencia verificada informativa; contribución neta cero. Inclusión aditiva fuera del incremento"],
    ]
    if missing:
        defects.append(["O2C-S2-VALID OPEN", "Evidencia incompleta", ", ".join(missing)])
    decision = {
        "status": status, "observed_at_utc": datetime.now(UTC).isoformat(), "release_validated": passed,
        "missing": missing, "counts": counts, "defects": defects,
        "production_deployed": False, "project14_written": False, "next_wave_started": False,
    }
    (QA / "release-decision.json").write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    (QA / "release-evidence.json").write_text(json.dumps({
        "junit": JUNIT, "date": "2026-11-18", "browser_evidence": "chromium-attempt-b/o2c-browser-evidence.json",
        "file_sha256": {str(path.relative_to(QA)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in [QA / file for file in JUNIT.values()] if path.exists()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(status)
    print(json.dumps({"counts": counts, "missing": missing}))


if __name__ == "__main__":
    main()
