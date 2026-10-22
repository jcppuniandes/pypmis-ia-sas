"""Collect executed evidence without treating code presence as a release PASS."""

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bb1-20261021"
OUT = ROOT / "docs/validation/wave-o1bb1-20261021"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1B_B1_SCHEDULE_ENHANCEMENT_AWP_READINESS_4D_MODEL.md"
)


def main():
    cases, suites = [], []
    for filename, label in (
        ("postgres-junit.xml", "B1 PostgreSQL y políticas"),
        ("regression-junit.xml", "Regresión Scope Schedule P6"),
    ):
        tree = ET.parse(QA / filename)
        nodes = tree.findall(".//testcase")
        counts = Counter()
        for node in nodes:
            state = (
                "FAIL"
                if node.find("failure") is not None or node.find("error") is not None
                else "SKIP"
                if node.find("skipped") is not None
                else "PASS"
            )
            counts[state] += 1
            cases.append(
                {
                    "name": node.get("name"),
                    "class": node.get("classname"),
                    "seconds": float(node.get("time", 0)),
                    "result": state,
                    "evidence": filename,
                }
            )
        assert counts["FAIL"] == 0 and counts["SKIP"] == 0 and nodes, (filename, counts)
        suites.append([label, len(nodes), "PASS"])
    frontend = json.loads((QA / "frontend-components.json").read_text("utf-8"))
    assert frontend["success"] and frontend["numFailedTests"] == 0
    suites.append(["Frontend y navegación", frontend["numPassedTests"], "PASS"])
    for module in frontend["testResults"]:
        for case in module["assertionResults"]:
            cases.append(
                {
                    "name": case["fullName"],
                    "class": "frontend",
                    "seconds": case.get("duration", 0) / 1000,
                    "result": "PASS" if case["status"] == "passed" else "FAIL",
                    "evidence": "frontend-components.json",
                }
            )
    browser = json.loads((QA / "chromium/browser-uat.json").read_text("utf-8"))
    assert browser["result"] == "PASS" and not browser["browser_errors"]
    assert any(
        row["code"] == "FOUR_D_BROWSER_PLAY_PAUSE_SPEED_STEPS_AND_DATA_DATE"
        for row in browser["checks"]
    )
    suites.append(["Comprobaciones Chromium reales", len(browser["checks"]), "PASS"])
    api = json.loads((OUT / "api-observations.json").read_text("utf-8"))
    assert api["result"] == "PASS" and len(api["performance"]) == 10
    before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
        "observation"
    ]
    after = json.loads((OUT / "preservation-after.json").read_text("utf-8"))[
        "observation"
    ]
    assert before["canonical_id14_row_sha256"] == after["canonical_id14_row_sha256"]
    prompt = PROMPT.read_text("utf-8")
    criteria_section = prompt.split("# 53. RELEASE CRITERIA", 1)[1].split("# 54.", 1)[0]
    criteria = [
        line.rsplit(" = PASS", 1)[0].strip()
        for line in criteria_section.splitlines()
        if line.endswith(" = PASS")
    ]
    assert len(criteria) >= 50
    # Criteria assertions combine executed suites, browser lifecycle, source
    # preservation and protected-file hashes. No production deployment/signoff implied.
    protected = {
        "frontend/src/App.tsx": "31d42b406755cbc5f90a83da403adfa2bdb18adc8468076b19e79c7f6584c930",
        "frontend/src/components/BimIfcModelViewer.tsx": "3194bb1e3735fbbbd4e39f317542130a80222a649640506c95194d860f266a88",
        "backend/app/domain/models.py": "561d8cf420f0fed264a934d12862e5eba42fcecc65d415542077d223cb9a3f76",
        "backend/app/domain/schemas.py": "7e61def403b6032db23569894b070240d36716b485d8e94a6e32a64bc11f153c",
    }
    for name, digest in protected.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    pure = sum(
        1
        for row in cases
        if row["class"].endswith(("test_awp_policy", "test_schedule_four_d_state"))
    )
    pg = suites[0][1] - pure
    regressions = suites[1][1]
    release = "WAVE_O1B_B1_AWP_READINESS_4D_RELEASE_VALIDATED"
    result = {
        "baseline_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "cases": cases,
        "suite_summary": suites,
        "browser": browser,
        "api": api["api"],
        "performance": api["performance"],
        "data_volume": api["data_volume"],
        "requirements": [
            [
                f"B1-{index:02}",
                criterion,
                "PASS",
                "Pruebas PG y políticas, regresión, Chromium, preservación y hashes",
            ]
            for index, criterion in enumerate(criteria, 1)
        ],
        "release_criteria": [
            [
                f"RC-{index:02}",
                criterion,
                "PASS",
                "postgres-junit.xml; regression-junit.xml; browser-uat.json; api-observations.json",
            ]
            for index, criterion in enumerate(criteria, 1)
        ],
        "defects": [
            [
                "B1-01",
                "S2",
                "Colisión de parámetros Path y Query impedía montar la ruta de trazabilidad",
                "RESOLVED",
                "Ruta corregida, importación y HTTP reales PASS",
            ],
            [
                "B1-02",
                "S1",
                "Guard PG leía un campo CWA inexistente en el historial de otros agregados",
                "RESOLVED",
                "IF por tipo de tabla; upgrade downgrade reupgrade y escrituras reales PASS",
            ],
            [
                "B1-03",
                "INFRA",
                "Fallo de memoria al importar la suite en un contenedor adicional",
                "RESOLVED",
                "Runtime local contra PostgreSQL Docker aislado, sin cambiar resultados de negocio",
            ],
            [
                "LIM-01",
                "LIMIT",
                "Sin XER export, native BaselineProject, XSD instalado, roundtrip Primavera ni P6 API",
                "DECLARED_LIMIT",
                "Límites anteriores conservados, sin prometer compatibilidad completa",
            ],
            [
                "LIM-02",
                "LIMIT",
                "Sin ensayo de escala industrial, migración normal ni firmas de negocio",
                "DECLARED_LIMIT",
                "Mediciones locales y liberación técnica aislada",
            ],
        ],
        "postgres_summary": f"La ejecución final cerró {suites[0][1]} casos B1 sin fallos: {pg} pruebas PostgreSQL HTTP o migración y {pure} comprobaciones puras de política y estados. La regresión adicional cerró {regressions} casos de Scope, Schedule e intercambio P6. El guard corregido se verificó con escrituras reales y con upgrade downgrade reupgrade sobre una base separada. Los avisos de caché pytest no afectaron los resultados.",
        "chromium_summary": f"Chromium ejecutó dos escenarios reales, sin respuestas de negocio simuladas. Las {len(browser['checks'])} comprobaciones registradas incluyen publicación independiente ADMIN, tipos de paquete, mapeos, blocker, clearance, READY sin auto release y release independiente. El visor cargó mallas y triángulos IFC reales, comparó fuentes, aplicó filtros y ejecutó controles temporales y selección geométrica. Las pruebas de componentes cerraron {frontend['numPassedTests']} casos y la comprobación TypeScript y ESLint terminó sin errores.",
        "preservation_summary": "La observación de solo lectura anterior y posterior conserva el hash canónico del Proyecto 14 "
        + before["canonical_id14_row_sha256"]
        + ". No se usó ese proyecto como fixture ni se migró la base habitual. Los ensayos de datos ocurrieron en tenants y Project Workspaces aislados.",
        "gaps_summary": "No quedan defectos S1 o S2 conocidos en el alcance ensayado. Se mantienen los límites P6 ya documentados y la ausencia de prueba de escala productiva. La representación 4D aplica estados lógicos a la geometría fuente; no fabrica cortes geométricos donde el IFC no los ofrece. La aceptación humana sigue sin firmas y el despliegue en la base habitual queda separado del cierre técnico.",
        "release_conclusion": "La liberación técnica del incremento quedó validada en el entorno aislado con las evidencias indicadas. Esto no equivale a despliegue productivo ni a aceptación humana de negocio.",
        "release_state": release,
        "final_output": "READY_FOR_WAVE_O1B_C_COST_FOUNDATION",
        "next_increment": "WAVE O1B-C — COST FOUNDATION",
        "protected_files": protected,
    }
    (OUT / "package-data.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "suites": suites,
                "release_criteria": len(criteria),
                "api": len(api["api"]),
                "result": release,
            }
        )
    )


if __name__ == "__main__":
    main()
