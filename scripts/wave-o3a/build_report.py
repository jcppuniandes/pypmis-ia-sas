"""Build the O3A Word report from the current evidence cut."""

import importlib.util
import json
import sys

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from report_content import BASELINE, DATE, OUT, QA, ROOT, matrix, read, sections, tests

# Reuse the verified typography/table helpers, not the former Wave's narrative.
sys.path.insert(0, str(ROOT / "scripts/wave-o2c"))
spec = importlib.util.spec_from_file_location(
    "o3a_word_helpers", ROOT / "scripts/wave-o2c/build_report.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.core_properties.title = "Operaciones de construcción O3A Informe técnico"
    doc.core_properties.subject = "Field Operations Manager"
    doc.core_properties.author = "P&Pmis Construction AI"
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "Aptos"
        style.font.color.rgb = RGBColor(0, 0, 0)
        for node in list(style.element.findall(".//" + qn("w:pBdr"))):
            node.getparent().remove(node)
    doc.styles["Normal"].font.size = Pt(11)
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.left_margin = section.right_margin = Inches(0.85)
    section.top_margin = section.bottom_margin = Inches(0.7)
    doc.add_paragraph("P&Pmis Construction AI")
    doc.add_paragraph("Operaciones de construcción O3A", style="Title")
    doc.add_paragraph("Informe técnico de Field Operations Manager", style="Subtitle")
    doc.add_paragraph(DATE)
    for title, content in sections():
        helpers.heading(doc, title)
        helpers.paragraph(doc, content)
    helpers.heading(doc, "Resultados registrados de pruebas")
    evidence = tests()
    if evidence:
        helpers.paragraph(
            doc,
            "Se presentan los resultados finales por suite. La suite execution policy contiene trece políticas que también aparecen en core policy; sus casos no deben sumarse como pruebas únicas. Los intentos anteriores se conservan como historial de validación, no como el resultado vigente.",
        )
        helpers.table(
            doc,
            ["Suite", "Casos", "Fallos", "Omitidos"],
            [
                [name.replace("-junit.xml", ""), count, failures + errors, skipped]
                for name, count, failures, errors, skipped, _ in evidence
            ],
            [3.7, 0.9, 1.0, 1.1],
        )
    perf = read("consumer-performance.json").get("reads", [])
    if perf:
        helpers.heading(doc, "Lecturas medidas en el entorno aislado")
        helpers.table(
            doc,
            ["Consulta", "Mediana ms", "Bytes"],
            [[row["query"], row["median_ms"], max(row["bytes"])] for row in perf],
            [3.9, 1.4, 1.4],
        )
    contracts = read("contracts-performance.json")
    if contracts:
        helpers.heading(doc, "Seguimiento de latencia Contracts")
        helpers.table(
            doc,
            ["Consulta", "Mediana ms", "Bytes"],
            [
                [name, record["median_ms"], record["median_response_bytes"]]
                for name, record in contracts["metrics"].items()
            ],
            [3.9, 1.4, 1.4],
        )
        helpers.paragraph(
            doc,
            "Tres consultas consecutivas por endpoint mediante ASGI TestClient con PostgreSQL real. Se verificaron cero escrituras SQL y once hashes canónicos iguales antes y después. Esta medición no cierra la deuda heredada ni establece un SLA.",
        )
    for filename, label in (
        ("execution-evidence.json", "Ejecución real de campo"),
        ("core-evidence.json", "Cadena de partes diarios"),
    ):
        record = read(filename)
        if record:
            helpers.heading(doc, label)
            # IDs and facts only; never serialize a credentials manifest.
            rows = []
            for key, value in record.items():
                if any(
                    part in key.lower()
                    for part in ("password", "credential", "token", "headers")
                ):
                    continue
                if isinstance(value, (str, int, float, bool)):
                    rows.append([key.replace("_", " "), str(value)])
            helpers.table(
                doc, ["Registro o control", "Valor observado"], rows, [3.9, 2.8]
            )
    browser = read("browser-summary.json")
    if browser.get("passed"):
        helpers.heading(doc, "Cadena comprobada en Chromium")
        helpers.paragraph(
            doc,
            f"La prueba completa aprobó {len(browser['steps'])} acciones reales y registró {len(browser.get('errors', []))} errores JavaScript. Incluyó el perfil ADMIN, la captura con materiales, el parte aprobado, el turno cerrado, los consumidores nativos y la vista móvil.",
        )
        helpers.table(
            doc,
            ["Registro", "Identificador"],
            [
                [key.replace("_", " "), value]
                for key, value in browser["observed"].items()
            ],
            [4.9, 1.8],
        )
    helpers.heading(doc, "Habilitación controlada posterior")
    helpers.paragraph(
        doc,
        "La base habitual no recibió migraciones ni catálogos nuevos. Para habilitar O3A en otro entorno se requiere aplicar Alembic 0080 con el procedimiento de despliegue autorizado, provisionar el catálogo mediante field_operations.provision con tenant y administrador explícitos, asignar los roles, habilitar field-operations en el proyecto y publicar un perfil por una persona distinta de quien lo preparó. No se crean hechos de obra ni asignaciones de usuarios durante el aprovisionamiento del catálogo.",
    )
    decision = read("release-decision.json")
    helpers.heading(doc, "Resultado del corte")
    helpers.paragraph(doc, decision.get("status", "VALIDACION EN CURSO"), bold=True)
    for note in decision.get("notes", []):
        helpers.paragraph(doc, note)
    for code, severity, description, status, action in decision.get("defects", []):
        helpers.paragraph(doc, f"{code} ({severity}, {status}). {description} {action}")
    helpers.paragraph(doc, "Baseline de referencia: " + BASELINE)
    target = OUT / "P&Pmis_Wave_O3A_Construction_Field_Operations_Technical_Report.docx"
    doc.save(target)
    (QA / "matrix-data.json").write_text(
        json.dumps(matrix(), ensure_ascii=False), encoding="utf-8"
    )
    print(target)


if __name__ == "__main__":
    main()
