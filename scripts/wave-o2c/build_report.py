"""Generate the Spanish technical report and workbook source data."""

import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from report_content import (
    BASELINE,
    DATE,
    QA,
    detailed_sections,
    matrix,
    read_json,
    sections,
    status,
)

CANDIDATE = QA / "final-candidate"
FILE = "P&Pmis_Wave_O2C_Contracts_Commitments_Technical_Report.docx"
INK = RGBColor.from_string("000000")
TEAL = RGBColor.from_string("000000")
GRAY = RGBColor.from_string("445B6A")


def text_style(run, *, size=10, color=INK, bold=False):
    run.font.name, run.font.size, run.font.color.rgb, run.bold = (
        "Aptos",
        Pt(size),
        color,
        bold,
    )


def paragraph(doc, text, *, size=11, color=INK, bold=False, after=8):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.12
    text_style(p.add_run(text), size=size, color=color, bold=bold)
    return p


def heading(doc, label):
    p = doc.add_heading(label, level=1)
    p.paragraph_format.space_before = Pt(13)
    p.paragraph_format.space_after = Pt(5)
    for run in p.runs:
        text_style(run, size=15, color=TEAL, bold=True)
    return p


def table(doc, headers, rows, widths):
    item = doc.add_table(rows=1, cols=len(headers))
    item.autofit = False
    for index, width in enumerate(widths):
        item.columns[index].width = Inches(width)
    header = item.rows[0]
    marker = OxmlElement("w:tblHeader")
    header._tr.get_or_add_trPr().append(marker)
    for values in [headers, *rows]:
        row = header if values is headers else item.add_row()
        for index, value in enumerate(values):
            cell = row.cells[index]
            cell.width = Inches(widths[index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text = str(value)
            tcpr = cell._tc.get_or_add_tcPr()
            padding = OxmlElement("w:tcMar")
            for edge in ("top", "left", "bottom", "right"):
                margin = OxmlElement(f"w:{edge}")
                margin.set(qn("w:w"), "100")
                margin.set(qn("w:type"), "dxa")
                padding.append(margin)
            tcpr.append(padding)
            borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right"):
                border = OxmlElement(f"w:{edge}")
                for key, val in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
                    border.set(qn(f"w:{key}"), val)
                borders.append(border)
            tcpr.append(borders)
            fill = OxmlElement("w:shd")
            fill.set(qn("w:fill"), "E7EDF2" if values is headers else "FFFFFF")
            tcpr.append(fill)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(5)
                p.paragraph_format.space_after = Pt(5)
                for run in p.runs:
                    text_style(run, size=10, bold=values is headers)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def report():
    doc = Document()
    doc.core_properties.title = "P&Pmis Construction AI | Wave O2C"
    doc.core_properties.subject = "Contracts & Commitments Foundation"
    for name in ("Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        doc.styles[name].font.color.rgb = INK
        for border in list(doc.styles[name].element.findall(".//" + qn("w:pBdr"))):
            border.getparent().remove(border)
    doc.styles["Normal"].font.name = "Aptos"
    doc.styles["Normal"].font.size = Pt(11)
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin, section.bottom_margin = Inches(0.7), Inches(0.72)
    section.left_margin = section.right_margin = Inches(0.87)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    text_style(
        footer.add_run("P&Pmis Construction AI  /  O2C  /  Validación técnica"),
        size=9,
        color=GRAY,
    )
    p = paragraph(
        doc,
        "P&PMIS CONSTRUCTION AI  /  OPERACIONES",
        size=11,
        color=TEAL,
        bold=True,
        after=22,
    )
    p.paragraph_format.space_before = Pt(36)
    title = doc.add_heading("Fundación de contratos y compromisos", level=0)
    for run in title.runs:
        text_style(run, size=28, bold=True)
    paragraph(
        doc,
        "Informe técnico Wave O2C",
        size=18,
        color=INK,
        after=20,
    )
    paragraph(doc, DATE + "  /  " + BASELINE, color=GRAY, after=18)
    paragraph(doc, status(), size=11, color=TEAL, bold=True, after=14)
    blocks = sections()
    for index, (label, items) in enumerate(blocks):
        heading(doc, label)
        for item in items:
            paragraph(doc, item)
    for label, items in detailed_sections():
        heading(doc, label)
        for item in items:
            paragraph(doc, item)
    heading(doc, "Escenario registrado")
    proof = read_json(QA / "core-attempt-a/scenario.json")
    if proof:
        table(
            doc,
            ["Registro", "Identificador", "Estado"],
            [
                [
                    "Workspace sintético",
                    proof["project_workspace_id"],
                    "Distinto de Proyecto 14",
                ],
                ["PO de origen", proof["po_id"], "Emitida por Procurement"],
                ["Contrato", proof["contract_id"], "EFFECTIVE"],
                ["Versión contractual", proof["contract_version_id"], "APPROVED"],
                [
                    "Compromiso comercial",
                    proof["commercial_commitment"]["id"],
                    "APPROVED",
                ],
                ["Adopción Cost", proof["cost_adoption"]["id"], "ADOPTED"],
                [
                    "Referencia financiera",
                    proof["financial_reference"]["id"],
                    "VERIFIED REFERENCE_ONLY",
                ],
            ],
            [2.2, 1.1, 3.1],
        )
    heading(doc, "Rendimiento defectos y decisión").paragraph_format.page_break_before = True
    metrics = read_json(QA / "performance-final.json")
    if metrics:
        paragraph(
            doc,
            "Lecturas API: tres muestras por consulta. Mediana observada y tamaño de respuesta.",
            color=GRAY,
        )
        table(
            doc,
            ["Consulta", "Mediana ms", "Respuesta bytes"],
            [
                [label, record["median_ms"], record["response_bytes"]]
                for label, record in metrics.items()
            ],
            [3.8, 1.3, 1.3],
        )
    else:
        paragraph(doc, "No se dispone de un juego completo de muestras del corte.")
    for code, title, notes in read_json(QA / "release-decision.json").get(
        "defects", []
    ):
        paragraph(doc, f"{code} — {title}: {notes}")
    paragraph(doc, "Decisión: " + status(), color=TEAL, bold=True)
    paragraph(doc, "No se inició otra Wave ni se desplegó a producción.", color=GRAY)
    doc.save(CANDIDATE / FILE)


if __name__ == "__main__":
    CANDIDATE.mkdir(parents=True, exist_ok=True)
    report()
    (CANDIDATE / Path("matrix-data.json")).write_text(
        json.dumps(matrix(), ensure_ascii=False), encoding="utf-8"
    )
