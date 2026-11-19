"""Append chapter 48 to the existing report using the selected release decision."""

import importlib.util
import io
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2b-close2-20261112"
STEM = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Technical_Report"
BASE = ROOT / "outputs/wave-o2b" / f"{STEM}.docx"
BASE_SHA = "42db2ca2d0f12942787342c829e0948517e02b96a2d6c2c90614911d2eb8bb48"
OUTPUT = QA / "artifacts/candidate" / f"{STEM}1.docx"


def main(attempt):
    summary = json.loads(
        (QA / "release" / f"decision-{attempt}.json").read_text("utf-8")
    )
    assert sha256(BASE.read_bytes()).hexdigest() == BASE_SHA
    template = importlib.util.spec_from_file_location(
        "report_styles", ROOT / "scripts/wave-o1bb1/generate_report.py"
    )
    assert template and template.loader
    styles = importlib.util.module_from_spec(template)
    template.loader.exec_module(styles)
    p, table = styles.p, styles.table
    doc = Document(BASE)
    old_paragraphs = [item.text for item in doc.paragraphs]
    original_nodes = list(doc._element.body)[:-1]
    assert sum(item.style.name == "Heading 1" for item in doc.paragraphs) == 47
    heading = doc.add_heading("48 Cierre final O2B.CLOSE-2", level=1)
    heading.paragraph_format.page_break_before = True
    p(doc, "P&Pmis Construction AI. Código congelado el 12 de noviembre de 2026.")
    p(
        doc,
        f"Decisión técnica: {summary['decision']}. O2B-G01: {summary['g01']}. O2B-G02: {summary['g02']}.",
    )
    if summary["readiness"]:
        p(doc, summary["readiness"])
    else:
        p(
            doc,
            "No se habilita el inicio de O2C. Los controles abiertos se detallan al final del capítulo.",
        )
    p(
        doc,
        "Este capítulo conserva el corte anterior como antecedente y registra solo la evidencia del corte CLOSE-2. "
        "No se desplegó producción, no se migró su base y no se implementó O2C.",
    )
    doc.add_heading("Cuatro controles de cierre", level=2)
    descriptions = {
        "CLOSE-PG-O1": "Se reconciliaron las pruebas Gate06D con scope-manager, schedule-manager y cost. "
        "Los cambios de catálogo de O1 precedían a O2B. Se conservaron los casos de acceso, rutas inválidas y denegación, sin cambiar la navegación productiva.",
        "CLOSE-PROG-LINEAGE": "El lector de Progress reconoce el estado SUPERSEDED del IWP. "
        "La prueba usa un vínculo sucesor para el mismo hecho de despacho. Verifica la nueva adopción, el rechazo de la referencia anterior y la conservación de la decisión histórica y de la autoridad de avance.",
        "CLOSE-FCST-SOURCES": "Se reutilizaron el forecast de fabricación del hito del proveedor y el de despacho de Expediting. "
        "La prueba distingue las fechas pronosticadas de las planificadas y cubre sucesión, versión, hash e inactivación. No se agregaron campos de fecha ni se recalculó Forecast.",
        "CLOSE-AUTH-WRITE": "El rol procurement_buyer se prueba primero dentro de su propio dominio. "
        "Los comandos ajenos prueban compromisos, presupuesto, costo real, medición, aprobación, período y versiones de Forecast. Las huellas SQL se comparan antes y después.",
    }
    for control in summary["controls"]:
        label = f"{control['id']} · {control['status']}"
        row = p(doc, label)
        if row is None:
            row = doc.paragraphs[-1]
        row.paragraph_format.keep_with_next = True
        for run in row.runs:
            run.bold = True
        p(doc, descriptions[control["id"]])
    if summary["auth_write_count"]:
        p(
            doc,
            f"Se rechazaron {summary['auth_write_count']} comandos con HTTP 403. Las huellas de 20 tablas protegidas coincidieron.",
        )
    if all(control["status"] == "CLOSED" for control in summary["controls"]):
        p(
            doc,
            "La evidencia detallada de los cuatro controles se conserva en las carpetas pg-o1, progress-lineage, forecast-sources y auth-write del corte.",
        )

    section = doc.add_heading("Regresiones y preservación", level=2)
    section.paragraph_format.page_break_before = True
    frozen = summary["freeze"]
    p(
        doc,
        f"Intento {attempt}. Git {frozen['git_commit']}. Alembic {frozen['alembic_head']}. "
        f"Se registraron {frozen['files']} huellas de código, pruebas y configuración. Fecha UTC: {frozen['timestamp'] or 'sin evidencia'}.",
    )
    table(
        doc,
        ["Carril", "Resultado", "Evidencia del corte"],
        [
            [
                label,
                f"{result['tests']['passed']} "
                + ("aprobada" if result["tests"]["passed"] == 1 else "aprobadas")
                if result["pass"]
                else f"{result['tests']['failed']} fallos"
                if result["tests"]["failed"]
                else "No acreditado",
                result["evidence"],
            ]
            for label, result in summary["regressions"].items()
        ],
        [1.66, 1.24, 3.20],
    )
    profiles = [
        result["published_profile"]
        for result in summary["regressions"].values()
        if result["published_profile"]
    ]
    if profiles:
        p(
            doc,
            "Perfiles publicados de Chromium: "
            + "; ".join(
                f"{item['code']} revisión {item['revision']}, versión {item['version']}"
                for item in profiles
            )
            + ". Los manifiestos conservan sus hashes.",
        )
    provenance = summary.get("profile_provenance", {})
    if provenance.get("verified"):
        p(
            doc,
            f"Se verificaron los perfiles publicados que respaldan {provenance['decisions']} decisiones de consumidores. "
            f"Sus revisiones, versiones y hashes están en {provenance['evidence']}.",
        )
    if summary.get("o2a_browser_attempt") != attempt:
        p(
            doc,
            "El primer intento de Engineering no cargó un recurso JavaScript local. Se conservó ese resultado y "
            "se repitió la prueba en otro tenant sintético, con la misma huella de código y sin modificar el test.",
        )
    p(
        doc,
        "El paquete de Procurement no es un PWP. Requisición, RFQ, oferta, adjudicación y PO conservan identidades distintas. "
        "La PO no crea contrato ni compromiso. Recibir, aceptar y disponer material son pasos distintos y no registran instalación. "
        "Engineering y Material aportan evidencia de preparación, pero AWP conserva la liberación del IWP.",
    )
    if summary["project14"]["preserved"]:
        item = summary["project14"]
        p(
            doc,
            f"Proyecto 14: la fila canónica conservó su huella. Dos observaciones de solo lectura compararon "
            f"{item['references']} conjuntos de referencias a la clave del proyecto legado. "
            + (
                "No se encontró la fila legada ni referencias a ella."
                if item["legacy_absent"]
                else "La fila legada y sus referencias conservaron sus huellas."
            ),
        )
    else:
        p(
            doc,
            "Proyecto 14: la comparación final de solo lectura aún no está acreditada.",
        )
    doc.add_heading("Defectos y decisión técnica", level=2)
    p(
        doc,
        "Controles abiertos por severidad: "
        + ", ".join(f"{k} = {v}" for k, v in summary["open_severity"].items())
        + ".",
    )
    for item in summary["blockers"]:
        p(
            doc,
            f"{item['id']} ({item['severity']}). Causa: {item['observation']} Evidencia: {item['evidence']}. Acción: {item['action']}",
        )
    if not summary["blockers"]:
        p(
            doc,
            "La validación técnica permite preparar el diseño de O2C. No autoriza despliegue ni inicia O2C.",
        )
    assert list(doc._element.body)[: len(original_nodes)] == original_nodes
    doc.core_properties.modified = datetime.now(UTC)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    doc.save(buffer)
    changed = {"docProps/core.xml", "word/document.xml"}
    with (
        ZipFile(BASE) as original,
        ZipFile(buffer) as edited,
        ZipFile(OUTPUT, "w") as final,
    ):
        for entry in original.infolist():
            final.writestr(
                entry,
                (edited if entry.filename in changed else original).read(
                    entry.filename
                ),
            )
    reopened = Document(OUTPUT)
    assert [
        item.text for item in reopened.paragraphs[: len(old_paragraphs)]
    ] == old_paragraphs
    assert sum(item.style.name == "Heading 1" for item in reopened.paragraphs) == 48
    print(OUTPUT)


if __name__ == "__main__":
    main(sys.argv[1])
