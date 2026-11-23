"""Author the O3B Word report with recorded evidence, never inferred test success."""

import importlib.util
import json

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from report_content import (
    BASELINE,
    DATE,
    MARKER,
    OUT,
    QA,
    ROOT,
    domain_rows,
    matrix,
    read,
    sections,
    status,
    tests,
)


def helpers():
    spec = importlib.util.spec_from_file_location(
        "o3b_word_tables", ROOT / "scripts/wave-o2c/build_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.core_properties.title = "Gestión de calidad e inspecciones O3B"
    doc.core_properties.subject = "Informe técnico de Quality Manager"
    doc.core_properties.author = "P&Pmis Construction AI"
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        style = doc.styles[name]
        style.font.name = "Aptos"
        style.font.color.rgb = RGBColor(0, 0, 0)
        for border in list(style.element.findall(".//" + qn("w:pBdr"))):
            border.getparent().remove(border)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.08
    doc.styles["Heading 1"].font.size = Pt(14)
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(0.7)
    section.left_margin = section.right_margin = Inches(0.85)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.paragraph_format.right_indent = Inches(0)
    footer.paragraph_format.left_indent = Inches(0)
    footer.paragraph_format.space_after = Pt(0)
    footer.paragraph_format.line_spacing = 1
    footer.add_run("P&Pmis Construction AI   O3B").font.size = Pt(9)
    # A single Word field run avoids a line-breaking trailing-space boundary at
    # the right margin when the PAGE result becomes two digits.
    footer.add_run("   Página ").font.size = Pt(9)
    page = OxmlElement("w:fldSimple")
    page.set(qn("w:instr"), "PAGE")
    page_run = OxmlElement("w:r")
    page_properties = OxmlElement("w:rPr")
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "18")
    page_properties.append(size)
    page_run.append(page_properties)
    page_text = OxmlElement("w:t")
    page_text.text = "1"
    page_run.append(page_text)
    page.append(page_run)
    footer._p.append(page)
    doc.add_paragraph("P&Pmis Construction AI")
    doc.add_paragraph("Gestión de calidad e inspecciones O3B", style="Title")
    doc.add_paragraph("Informe técnico de Quality Manager", style="Subtitle")
    doc.add_paragraph(DATE)
    tables = helpers()
    for label, paragraphs in sections():
        heading = doc.add_heading(label, level=1)
        heading.paragraph_format.space_before = Pt(12)
        heading.paragraph_format.space_after = Pt(5)
        for text in paragraphs:
            doc.add_paragraph(text)
        if label.startswith("04 "):
            tables.table(
                doc,
                ["Dominio", "Hecho autorizado"],
                [
                    ["Quality", "Conformidad y aceptación técnica"],
                    ["Progress", "Avance certificado y aprobado"],
                    ["AWP", "Readiness y liberación del paquete"],
                    ["Contracts y Cost", "Consecuencias comerciales y financieras"],
                ],
                [1.7, 5.0],
            )
        if label.startswith("30 "):
            tables.table(
                doc,
                ["Control", "Respuesta esperada"],
                [
                    ["Sin permiso", "403"],
                    ["Identidad fuera de alcance", "404"],
                    ["Estado inválido o clave reutilizada con otro cuerpo", "409"],
                    ["If Match vencido", "412"],
                ],
                [5.3, 1.4],
            )
        if label.startswith("32 "):
            migration = read("migration/round-trip.json")
            if migration:
                tables.table(
                    doc,
                    ["Control observado", "Resultado"],
                    [
                        ["HEAD posterior", migration.get("initial_upgrade")],
                        [
                            "Tablas tras bajar a 0080",
                            migration.get("empty_round_trip", [{}])[0].get(
                                "quality_tables"
                            ),
                        ],
                        [
                            "Tablas tras volver a 0081",
                            migration.get("scoped_guarded_tables"),
                        ],
                        ["Triggers O3B", migration.get("guard_triggers")],
                        ["Resultado", migration.get("status")],
                    ],
                    [4.9, 1.8],
                )
        if label.startswith("33 "):
            rows = tests()
            if rows:
                tables.table(
                    doc,
                    ["Suite", "Casos", "Fallos", "Omitidos"],
                    [
                        [
                            name.replace("-junit.xml", "")
                            .replace("/", " / ")
                            .replace("-", " "),
                            count,
                            failed + error,
                            skipped,
                        ]
                        for name, count, failed, error, skipped, _ in rows
                    ],
                    [3.8, 0.9, 1.0, 1.0],
                )
            remediation = read("execution/real-remediation.json")
            consumer = read("consumer-evidence.json")
            if remediation and consumer:
                doc.add_paragraph(
                    "Las cadenas de remediación y de consumidores utilizan tenants sintéticos independientes. Las siguientes identidades permiten localizar sus hechos reales sin confundir ambas cadenas."
                )
                tables.table(
                    doc,
                    ["Cadena", "Identidad observada", "Valor"],
                    [
                        ["Remediación", key, remediation[key]]
                        for key in (
                            "tenant_id",
                            "project_workspace_id",
                            "original_production_id",
                            "failed_inspection_id",
                            "ncr_id",
                            "real_field_rework_id",
                            "reinspection_id",
                            "successor_acceptance_id",
                            "receiving_acceptance_id",
                        )
                    ]
                    + [
                        ["Consumidores", key, consumer[key]]
                        for key in (
                            "tenant_id",
                            "workspace_id",
                            "acceptance_id",
                            "progress_decision_id",
                            "assessment_id",
                            "awp_decision_id",
                            "native_progress_approved",
                        )
                    ],
                    [1.2, 4.5, 1.0],
                )
        if label.startswith("34 "):
            browser = read("browser-summary.json")
            if browser:
                doc.add_paragraph(
                    f"Resultado registrado: {browser.get('status', browser.get('passed'))}. Acciones: {len(browser.get('steps', []))}. Errores JavaScript: {len(browser.get('errors', []))}."
                )
                doc.add_paragraph(
                    "La cadena Chromium conserva Acceptance 6 sucesora de 4, FAIL 17, reinspección PASS 19 y NCR 4 cerrada. Progress 34 conserva su numerador acumulado 1.6 después del vínculo Quality. El límite temporal de esta evidencia se complementa con las pruebas PostgreSQL finales del control de cantidades."
                )
        if label.startswith("35 "):
            observed = read("project-14/preservation-after.json").get("observation", {})
            if observed:
                doc.add_paragraph(
                    f"Comparación aprobada de {len(observed['project14_references'])} referencias legacy y {len(observed['canonical_workspace14_references'])} referencias al workspace canónico. Se verificaron identidad, conteos y hashes antes y después mediante transacciones de solo lectura."
                )
        if label.startswith("36 "):
            performance = read("consumer-performance.json").get("reads", [])
            if performance:
                tables.table(
                    doc,
                    ["Consulta", "Mediana ms", "Bytes máximos"],
                    [
                        [row["query"], row["median_ms"], max(row["bytes"])]
                        for row in performance
                    ],
                    [3.7, 1.5, 1.5],
                )
            contracts = read("contracts-performance.json")
            if contracts:
                tables.table(
                    doc,
                    ["Consulta Contracts", "Mediana ms", "Bytes"],
                    [
                        [key, value["median_ms"], value["median_response_bytes"]]
                        for key, value in contracts["metrics"].items()
                    ],
                    [3.7, 1.5, 1.5],
                )
        if label.startswith("38 "):
            defects = read("release-decision.json").get("defects", [])
            for code, severity, description, state, evidence in defects:
                doc.add_paragraph(
                    f"{code}. {severity}. {state}. {description} {evidence}"
                )
        if label.startswith("39 ") and status() == MARKER:
            paragraph = doc.add_paragraph()
            paragraph.add_run(MARKER).font.size = Pt(8)
    doc.add_heading("Anexo Modelo físico y fuentes de verificación", level=1)
    doc.add_paragraph(
        "Las entidades heredan tenant, workspace, creador, fecha y versión. QualityRecord agrega información de perfil y hash. La matriz Excel complementaria conserva los campos propios y contratos de cada entidad."
    )
    tables.table(
        doc,
        ["Entidad", "Tabla"],
        [[name, table] for name, table, *_ in domain_rows()],
        [3.2, 3.5],
    )
    doc.add_paragraph(
        "Las pruebas y actas de validación se conservan en el directorio QA de O3B. La matriz identifica suite, resultado y referencia. Baseline de código: "
        + BASELINE
        + "."
    )
    doc.add_paragraph(
        "Fuente de alcance: P&Pmis Wave O3B Quality Management Inspection Foundation Prompt Codex, apartados 1 a 68."
    )
    target = OUT / "P&Pmis_Wave_O3B_Quality_Management_Inspection_Technical_Report.docx"
    doc.save(target)
    (QA / "matrix-data.json").write_text(
        json.dumps(matrix(), ensure_ascii=False), encoding="utf-8"
    )
    print(target)


if __name__ == "__main__":
    main()
