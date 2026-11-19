"""Narrow edits and closeout controls for the existing traceability matrix."""

import json
import sys

from closeout_evidence import verdict
from freeze import QA


def main(attempt):
    e = verdict(attempt)
    checked = {row[0]: row[5] for row in e["controls"]}
    patch = {}

    def put(sheet, cell, value):
        patch.setdefault(sheet, {})[cell] = value

    def status(check):
        return "Verificado" if checked[check] else "Pendiente"

    put("00_README", "B8", f"{e['decision']}. G01: {e['g01']}. G02: {e['g02']}.")
    put(
        "00_README",
        "B9",
        f"P&Pmis Construction AI. Base Git e5747a6; cierre {attempt} en Alembic 20261111_0078.",
    )
    put(
        "00_README",
        "B10",
        "Prompt O2B base y O2B.CLOSE. Ver controles de cierre en 16_RELEASE_CRITERIA.",
    )
    for row, domain, explanation in (
        (33, "cost", "Orden, revisión y mapeos financieros. No crea compromisos."),
        (34, "progress", "Evidencia física en período abierto. No registra instalado."),
        (35, "forecast", "Señal fechada en borrador. No modifica forecast aprobado."),
    ):
        kind = f"CLOSE-{domain.upper()}"
        put("01_REQUIREMENTS", f"E{row}", "procurement_consumers/router.py")
        put(
            "01_REQUIREMENTS",
            f"F{row}",
            f"/api/v1/{domain}/projects/{{id}}/procurement-adoptions",
        )
        put("01_REQUIREMENTS", f"G{row}", f"test_procurement_{domain}_consumer_release")
        put(
            "01_REQUIREMENTS",
            f"H{row}",
            f"{kind}: " + ("PASS" if checked[kind] else "sin aprobación final"),
        )
        put("01_REQUIREMENTS", f"I{row}", status(kind))
        put("01_REQUIREMENTS", f"J{row}", explanation)
        put("08_INTEGRATIONS", f"B{row - 20}", explanation)
        put("08_INTEGRATIONS", f"C{row - 20}", "procurement_consumers/router.py")
    for row, key, note in (
        (
            49,
            "CLOSE-PG-O1",
            "O1, O2A y O2B se rastrean por separado en los controles de cierre.",
        ),
        (
            51,
            "CLOSE-MIG",
            "Reproducción desde PostgreSQL vacío con DDL original previo a Alembic.",
        ),
        (53, "CLOSE-WEB-O2B", "O2A y O2B incluyen ciclo real y contexto operacional."),
    ):
        put("01_REQUIREMENTS", f"H{row}", key)
        put("01_REQUIREMENTS", f"I{row}", status(key))
        put("01_REQUIREMENTS", f"J{row}", note)
    for row, note in (
        (8, "Decisión explícita de referencia. Award y PO no crean compromiso."),
        (9, "CBS, código y cuenta activos, verificados antes de adoptar."),
        (10, "Progress conserva la disposición física sin generar avance."),
        (11, "Forecast guarda la señal contra versión borrador sin publicar."),
    ):
        put("12_COST_TRACEABILITY", f"C{row}", note)
    for row, key in (
        (11, "CLOSE-MIG"),
        (12, "CLOSE-PG-O2A"),
        (13, "CLOSE-PG-O1"),
        (14, "CLOSE-WEB-O2B"),
    ):
        item = next(row for row in e["controls"] if row[0] == key)
        put(
            "14_TESTS", f"C{row}", f"{key}: " + ("PASS" if item[5] else "No acreditado")
        )
        put("14_TESTS", f"D{row}", item[4])
    put("14_TESTS", "B11", "test_procurement_o2b_close_history_migration.py")
    put("14_TESTS", "B14", "Ciclo Procurement y contexto canónico")
    o1 = next((row for row in e["blockers"] if row["control"] == "CLOSE-PG-O1"), None)
    o1_note = (
        f"CLOSE-PG-O1 (S2): {len(o1['failures'])} fallos. "
        f"{len(o1['baseline_reproduced'])} reproducidos en código previo."
        if o1 and o1["failures"]
        else "Ver controles CLOSE-MIG, CLOSE-PG y CLOSE-WEB."
    )
    put(
        "15_DEFECTS",
        "B8",
        f"Regresión histórica, suites O1/O2A/O2B y Chromium crítico. {o1_note}",
    )
    put("15_DEFECTS", "C8", e["g01"])
    put(
        "15_DEFECTS",
        "B9",
        "Adopción HTTP aprobada en los tres consumidores. Siguen abiertos reemplazos, señales Forecast y prueba de escritura directa. Ver los controles S2.",
    )
    put("15_DEFECTS", "C9", e["g02"])
    for row, label, reference, state in (
        (
            9,
            "Cadena histórica y reversión 0078 a 0075",
            "CLOSE-MIG",
            status("CLOSE-MIG"),
        ),
        (10, "Proyecto 14 preservado", "CLOSE-P14", status("CLOSE-P14")),
        (
            11,
            "Chromium crítico O2A y O2B",
            "CLOSE-WEB-O2A y CLOSE-WEB-O2B",
            "Verificado"
            if checked["CLOSE-WEB-O2A"] and checked["CLOSE-WEB-O2B"]
            else "Pendiente",
        ),
        (12, "Seis lecturas con tres muestras", "CLOSE-PERF", status("CLOSE-PERF")),
        (
            13,
            "Regresión histórica y adopción",
            f"G01: {e['g01']}. G02: {e['g02']}.",
            "Verificado" if e["g01"] == e["g02"] == "CLOSED" else "Parcial",
        ),
        (
            14,
            "Liberación O2B",
            e["decision"],
            "Verificado" if e["readiness"] else "Pendiente",
        ),
    ):
        for column, value in zip("ABC", (label, reference, state), strict=True):
            put("16_RELEASE_CRITERIA", f"{column}{row}", value)
    blockers = {row["control"]: row for row in e["blockers"]}
    controls = [
        [
            identity,
            requirement,
            implementation,
            test,
            evidence,
            "PASS"
            if result
            else "FAIL"
            if blockers[identity]["failures"]
            else "No acreditado",
            "CLOSED" if result else "OPEN",
            note
            if result
            else f"{blockers[identity]['severity']}: {blockers[identity]['action']}",
        ]
        for identity, requirement, implementation, test, evidence, result, note in e[
            "controls"
        ]
    ]
    output = QA / "artifacts" / "matrix-edits.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"patch": patch, "controls": controls}, ensure_ascii=False, indent=2
        ),
        "utf-8",
    )
    print(output)


if __name__ == "__main__":
    main(sys.argv[1])
