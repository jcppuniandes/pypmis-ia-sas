"""Append the closeout to the retained report, preserving its original pages."""

import importlib.util
import io
import sys
from datetime import UTC, datetime
from zipfile import ZipFile

from closeout_evidence import verdict
from docx import Document
from freeze import QA, ROOT

NAME = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Technical_Report.docx"
O1_DETAILS = {
    "test_project_property_facility_and_warehouse_contexts": "El menú ya no usa las etiquetas Scope, Schedule y Cost.",
    "test_open_home_recent_last_route_and_security_events": "Guardar /scope como última ruta devolvió HTTP 409; la ruta vigente usa scope-manager.",
    "test_module_permission_filtering_and_disabled_module_denial": "Consultar el código de módulo scope devolvió HTTP 403; el código vigente es scope-manager.",
}


def main(attempt):
    e = verdict(attempt)
    base = QA / "artifacts" / "baseline" / NAME
    output = QA / "artifacts" / "candidate" / NAME
    spec = importlib.util.spec_from_file_location(
        "ppmis_styles", ROOT / "scripts/wave-o1bb1/generate_report.py"
    )
    assert spec and spec.loader
    components = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(components)
    p, h, table = components.p, components.h, components.table

    def lane_result(key, passed):
        if key == "CLOSE-MIG":
            return "4/4 PASS" if passed else "No acreditado"
        wave = key.rsplit("-", 1)[-1].lower()
        if key.startswith("CLOSE-PG"):
            counts = e["pg"][wave].get("status_counts", {})
            if counts:
                return (
                    f"{counts['passed']}/{counts['total']} PASS"
                    if passed
                    else (f"{counts['failed']} fallos; {counts['error']} errores")
                )
        if key.startswith("CLOSE-WEB") and passed:
            return "2/2 PASS"
        return "No acreditado"

    doc = Document(base)
    assert sum(row.style.name == "Heading 1" for row in doc.paragraphs) == 39
    doc.core_properties.modified = datetime.now(UTC)
    h(doc, "40 Actualización de cierre O2B")
    doc.paragraphs[-1].paragraph_format.page_break_before = True
    p(
        doc,
        f"Decisión técnica: {e['decision']}. El informe anterior, secciones 1 a 39, queda como antecedente. "
        f"En este corte, O2B-G01 está {e['g01']} y O2B-G02 está {e['g02']}. "
        "Se implementó y probó la adopción, pero no se acreditaron todos los casos obligatorios.",
    )
    p(
        doc,
        "El alcance termina en la adopción de referencias. No se crearon contratos, compromisos, asientos, "
        "mediciones de avance ni versiones de pronóstico por el hecho de emitir, recibir o adoptar una fuente de compras.",
    )
    h(doc, "41 Fuente congelada y regresión histórica")
    frozen = e["freeze"]
    source = frozen.get("source", {})
    p(
        doc,
        f"Corte {attempt}. Git: {source.get('git_commit', 'no verificado')}. Alembic: "
        f"{source.get('alembic_head', 'no verificado')}. Se registraron {len(source.get('sha256', {}))} huellas "
        f"de archivos, configuración y pruebas. Fecha UTC: {frozen.get('frozen_at_utc', 'sin evidencia')}.",
    )
    history = e["migration"]
    if history:
        p(
            doc,
            f"Una base físicamente vacía de PostgreSQL {history['postgres_version']} recibió el DDL "
            "pre-Alembic recuperado del código original. Desde ese esquema, Alembic ejecutó "
            f"{history['alembic_revisions']} revisiones hasta {history['head']}, sin sellar revisiones a mano. "
            "Se verificaron columnas, restricciones, índices, triggers y la conservación de la identidad canónica. "
            "En la base descartable se repitió el tramo O2A a O2B.CLOSE tras bajar a 0075.",
        )
    else:
        p(
            doc,
            "No hay evidencia final de la cadena histórica. El ensayo preliminar queda separado del cierre.",
        )
    table(
        doc,
        ["Carril", "Resultado final", "Evidencia"],
        [
            [label, lane_result(key, passed), evidence]
            for key, label, _, _, evidence, passed, _ in e["controls"]
            if key.startswith(("CLOSE-PG", "CLOSE-WEB")) or key == "CLOSE-MIG"
        ],
        [2.15, 1.32, 2.63],
    )
    p(
        doc,
        "El cierre de G01 exige el catálogo histórico íntegro, las regresiones O1, O2A y O2B y los dos "
        "recorridos de navegador. Engineering mantiene la liberación IFC; solo AWP puede liberar un paquete.",
    )
    if o1_counts := e["pg"]["o1"].get("status_counts"):
        p(
            doc,
            f"O1 ejecutó {o1_counts['total']} casos: {o1_counts['passed']} aprobados, "
            f"{o1_counts['failed']} fallidos y {o1_counts['skipped']} omitidos.",
        )
    for wave, proof in e["browsers"].items():
        profile = proof.get("published_profile")
        if profile:
            p(
                doc,
                f"Perfil Chromium {wave.upper()}: {profile['code']} (ID {profile['id']}), revisión "
                f"{profile['revision']}, versión {profile['version']}. Huella en browser-source-proof.json.",
            )
    p(
        doc,
        "Chromium mantuvo el IWP sin liberar. Engineering READY y Material READY no equivalen a IWP RELEASED.",
    )
    h(doc, "42 Adopción desde Cost")
    doc.paragraphs[-1].paragraph_format.page_break_before = True
    p(
        doc,
        "Cost consulta la fuente en su propio espacio de proyecto y guarda una decisión explícita de referencia. "
        "La decisión fija origen Procurement, tipo, ID, versión, SHA-256, fecha observada y efectiva, política vigente "
        "y los tres mapeos aprobados de CBS, código de costo y cuenta de control. No crea un Commitment ni modifica el presupuesto o los costos reales.",
    )
    h(doc, "43 Adopción desde Progress")
    p(
        doc,
        "Progress registra evidencia para un período abierto. Los orígenes de inspección, despacho, llegada, "
        "recepción y disposición de calidad mantienen identidades distintas. El registro distingue cantidades aceptadas, "
        "rechazadas y en cuarentena. No mide cantidades instaladas ni cambia el avance físico.",
    )
    h(doc, "44 Adopción desde Forecast")
    p(
        doc,
        "Forecast registra una señal elegida contra el ID y versión de un borrador y su período. "
        "La decisión conserva fecha de origen, versión, hash y condición ADOPTED o NOT_ADOPTED. Un borrador no se "
        "recalcula por esa acción. Un Forecast aprobado no se modifica ni acepta decisiones por esa ruta.",
    )
    table(
        doc,
        ["Consumidor", "Validación del contrato", "Autoridad preservada"],
        [
            [
                "Cost",
                "PASS" if e["adoption"]["cost"] else "No acreditada",
                "Orden o adjudicación no es compromiso",
            ],
            [
                "Progress",
                "PASS" if e["adoption"]["progress"] else "No acreditada",
                "Recepción o aceptación no es instalación",
            ],
            [
                "Forecast",
                "PASS" if e["adoption"]["forecast"] else "No acreditada",
                "Señal no es forecast aprobado",
            ],
        ],
        [1.14, 1.75, 3.21],
    )
    h(doc, "45 Concurrencia y trazabilidad")
    p(
        doc,
        "La revisión 0078 agrega un registro append-only de decisiones. Los servicios de cada consumidor "
        "aplican sus permisos de lectura y escritura, además de lectura de Procurement. If-Match protege la versión de la "
        "decisión y una llave de idempotencia evita registros duplicados. El origen se vuelve a resolver antes de aceptar el registro.",
    )
    if e["consumer_profiles"]:
        profiles = "; ".join(
            f"{row['consumer'].title()} ID {row['id']}, rev. {row['revision']}, v{row['version']}"
            for row in e["consumer_profiles"]
        )
        p(
            doc,
            f"Políticas publicadas: {profiles}. Huellas y JUnit en postgres/consumer-{attempt}/.",
        )
    p(
        doc,
        "El JUnit suma tres recorridos HTTP en PostgreSQL y cuatro pruebas de resolución y políticas. Las pruebas de resolución no sustituyen los casos HTTP pendientes.",
    )
    h(doc, "46 Proyecto 14 y rendimiento")
    doc.paragraphs[-1].paragraph_format.page_break_before = True
    preservation = e["preservation"]
    if preservation:
        legacy = (
            "La fila legacy no existe en la base observada."
            if preservation["legacy_project14"] is None
            else "La fila legacy conserva su huella."
        )
        p(
            doc,
            f"La fila canónica y {len(preservation['project14_references'])} conjuntos de referencias "
            f"conservaron sus huellas antes y después. {legacy} La consulta usó una transacción de solo lectura.",
        )
    else:
        p(
            doc,
            "No se acreditó la comparación final de Proyecto 14. No se autorizó ninguna escritura.",
        )
    observations = e["performance"].get("operations", [])
    if observations:
        p(
            doc,
            "Tres consultas por operación sobre API local y PostgreSQL aislado. Las mediciones no representan un SLA.",
        )
        table(
            doc,
            ["Consulta", "Muestras ms", "Mediana ms", "Bytes"],
            [
                [
                    row["operation"],
                    " / ".join(f"{value:.1f}" for value in row["samples_ms"]),
                    f"{row['median_ms']:.1f}",
                    str(row["response_bytes"]),
                ]
                for row in observations
            ],
            [2.28, 1.78, 1.07, 0.97],
        )
    else:
        p(
            doc,
            "Las seis mediciones requeridas no se acreditaron en la ejecución seleccionada.",
        )
    h(doc, "47 Defectos y decisión de liberación")
    if e["blockers"]:
        p(
            doc,
            f"Quedan {len(e['blockers'])} controles S2 abiertos. No se detectaron hallazgos S1 en las pruebas ejecutadas.",
        )
        for row in e["blockers"]:
            details = [
                O1_DETAILS.get(
                    issue["case"].rsplit(".", 1)[-1],
                    issue["message"],
                )
                for issue in row["failures"]
            ]
            p(
                doc,
                f"{row['control']} ({row['severity']}). Evidencia: {row['evidence']}. "
                + f"Acción: {row['action']}",
            )
            if details:
                p(doc, " ".join(details))
            if row["baseline_reproduced"]:
                p(
                    doc,
                    f"{len(row['baseline_reproduced'])} fallos se reprodujeron en el código previo con SQLite aislado. "
                    f"La comparación no sustituye PostgreSQL. Evidencia: {e['baseline_comparison']}.",
                )
        p(doc, "La liberación formal queda bloqueada. No se autoriza el inicio de O2C.")
    else:
        p(
            doc,
            f"No quedaron controles bloqueantes S1 o S2 en el alcance validado. {e['decision']}.",
        )
        p(doc, e["readiness"])
    p(
        doc,
        "Este corte no despliega ni migra la base productiva y no inicia O2C. La matriz existente identifica "
        "la implementación, prueba, archivo de evidencia y resultado de cada control.",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    doc.save(buffer)
    with (
        ZipFile(base) as source_zip,
        ZipFile(buffer) as edited,
        ZipFile(output, "w") as final,
    ):
        changed = {"docProps/core.xml", "word/document.xml"}
        for entry in source_zip.infolist():
            final.writestr(
                entry,
                (edited if entry.filename in changed else source_zip).read(
                    entry.filename
                ),
            )
    retained = Document(base)
    updated = Document(output)
    assert [p.text for p in updated.paragraphs[: len(retained.paragraphs)]] == [
        p.text for p in retained.paragraphs
    ]
    assert sum(row.style.name == "Heading 1" for row in updated.paragraphs) == 47
    print(output)


if __name__ == "__main__":
    main(sys.argv[1])
