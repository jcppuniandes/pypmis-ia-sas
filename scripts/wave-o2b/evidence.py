"""Read saved validation observations without promoting partial proof to release."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2b"
OUT = ROOT / "outputs/wave-o2b"
DOCS = ROOT / "docs/validation/wave-o2b"


def load(path):
    return json.loads(path.read_text("utf-8-sig")) if path.is_file() else {}


def junit(path, module=None):
    if not path.is_file():
        return None
    cases = [
        case
        for case in ET.parse(path).iter("testcase")
        if not module or case.get("classname", "").split(".")[-1] == module
    ]
    result = {state: 0 for state in ("passed", "failed", "error", "skipped")}
    for case in cases:
        state = next(
            (
                tag
                for tag in ("failure", "error", "skipped")
                if case.find(tag) is not None
            ),
            "passed",
        )
        result["failed" if state == "failure" else state] += 1
    return result


def suite_text(result):
    if not result:
        return "Sin evidencia JUnit."
    return (
        f"{result['passed']} aprobadas, {result['failed']} fallidas, "
        f"{result['error']} errores y {result['skipped']} omitidas."
    )


def observations():
    critical = junit(QA / "pg-o2b.xml")
    final_critical = junit(QA / "pg-o2b-final.xml")
    critical_path = QA / ("pg-o2b-final.xml" if final_critical else "pg-o2b.xml")
    regression = junit(QA / "pg-o2a-regression.xml")
    additional = junit(QA / "operational-regression.xml")
    migration_paths = sorted(
        QA.glob("*migration*.xml"), key=lambda p: p.stat().st_mtime_ns
    )
    migration = junit(migration_paths[-1]) if migration_paths else None
    browser_paths = sorted(
        QA.rglob("browser-uat.json"), key=lambda p: p.stat().st_mtime_ns
    )
    browser = load(browser_paths[-1]) if browser_paths else {}
    perf = (
        load(browser_paths[-1].with_name("performance.json")) if browser_paths else {}
    )
    exact_perf = load(QA / "local-performance.json")
    if exact_perf.get("project_workspace_id") == browser.get(
        "project_workspace_id"
    ) and exact_perf.get("operations"):
        perf = exact_perf
    before, after = (
        load(DOCS / f"preservation-{phase}.json").get("observation", {})
        for phase in ("before", "after")
    )
    equal_keys = (
        "canonical_id14_row_sha256",
        "project14_row_sha256",
        "project14_references",
    )
    preserved = bool(
        before
        and after
        and all(before.get(key) == after.get(key) for key in equal_keys)
    )
    migration_text = suite_text(migration)
    if not migration:
        migration_text = "se observó una primera ida y vuelta aislada; la prueba JUnit final queda pendiente."
    browser_result = browser.get("result", "PENDIENTE")
    browser_text = (
        f"Última corrida registrada: {browser_result}. Última etapa registrada: {browser['stage']}. "
        "La prueba se dirige a API y PostgreSQL aislados, con un workspace sintético."
        if browser.get("stage")
        else "El guion de Playwright está implementado, pero este corte no dispone de una ejecución completa verificada."
    )
    if browser_result == "PASS":
        observed = browser["observations"]
        browser_text = (
            f"Chromium completó {len(browser['checks'])} controles del recorrido y registró "
            f"{len(browser['browser_errors'])} errores de navegador. En el workspace sintético "
            f"{browser['project_workspace_id']}, la evaluación AWP {observed['awp_assessment_id']} quedó "
            f"{observed['awp_readiness_state']} y el IWP conservó {observed['awp_release_state']}. "
            "Se guardaron capturas de ADMIN, compras, logística, recepción, disponibilidad, AWP e historial."
        )
    operations = perf.get("operations", [])
    performance_text = (
        f"Se midieron {len(operations)} de 8 operaciones. Cantidad de paquetes en el registro: {perf.get('register_size', 'n/d')}."
        if operations
        else "No hay muestras verificadas de las ocho operaciones en este corte."
    )
    gaps = []
    if browser_result != "PASS":
        gaps.append(
            "Falta aprobar el recorrido completo en Chromium y conservar sus capturas."
        )
    if len(operations) != 8 or any(
        len(item["samples_ms"]) < 3 or "record_count" not in item for item in operations
    ):
        gaps.append(
            "Faltan las muestras completas de rendimiento de las ocho operaciones."
        )
    if not final_critical or final_critical["failed"] or final_critical["error"]:
        gaps.append(
            "Falta confirmar el recorrido crítico sobre la última revisión de las fuentes."
        )
    if (
        not migration
        or migration["failed"]
        or migration["error"]
        or migration["skipped"]
    ):
        gaps.append(
            "Falta confirmar la ida y vuelta de la migración final con evidencia JUnit."
        )
    gaps.extend(
        [
            "Las regresiones abarcaron las suites operacionales y O2A; no se repitieron todas las migraciones históricas de O1 ni sus recorridos de navegador.",
            "Cost, Progress y Forecast pueden consultar hechos O2B. Queda por validar la adopción controlada de estas referencias desde los módulos consumidores.",
        ]
    )
    return {
        "decision": "Implementación funcional con validación parcial. No se declara la liberación de O2B.",
        "gaps": gaps,
        "pg_text": "Primera ejecución satisfactoria: "
        + suite_text(critical)
        + (
            " Reejecución final: " + suite_text(final_critical)
            if final_critical
            else ""
        ),
        "regression_text": "Regresión O2A y políticas de integración: "
        + suite_text(regression)
        + (
            " Regresión operacional adicional: " + suite_text(additional)
            if additional
            else ""
        ),
        "browser_text": browser_text,
        "migration_text": migration_text,
        "preservation_text": (
            f"La lectura antes y después coincide para la fila canónica, la fila histórica y "
            f"{len(after['project14_references'])} conjuntos de referencias. La fila legacy con ID 14 no existe en esta base; "
            f"el workspace canónico sí se observó y mantuvo la huella SHA-256 {after['canonical_id14_row_sha256']}. "
            "La observación se ejecutó con una transacción de solo lectura."
            if preserved
            else "La comparación de solo lectura antes y después no está acreditada en este corte."
        ),
        "performance_text": performance_text,
        "operations": operations,
        "critical": final_critical or critical,
        "critical_case": junit(critical_path, "test_procurement_o2b_release"),
        "sourcing_cases": junit(critical_path, "test_procurement_sourcing_policy"),
        "material_cases": junit(
            critical_path, "test_procurement_material_availability"
        ),
        "regression": regression,
        "additional": additional,
        "migration": migration,
        "browser_result": browser_result,
        "browser_stage": browser.get("stage"),
        "preserved": preserved,
    }
