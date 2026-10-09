from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from gate07i_report_data import SECTIONS

REPO = Path(__file__).resolve().parents[1]
OUTPUT = (
    REPO
    / "outputs"
    / "technical_reports"
    / "Informe_Tecnico_Gate_07I_Portfolio_Scenario_Convergence_20260826.docx"
)
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"

# Resolved document token map:
# preset=standard_business_brief; first-page pattern=memo_masthead.
# Named overrides: title=25pt; compact evidence callout=9.4pt; chapter page breaks.
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
INK = "0B2545"
BLACK = "000000"
MUTED = "5F6B76"
WHITE = "FFFFFF"
LIGHT = "F2F4F7"
ALT_LIGHT = "FAFBFC"
CALLOUT = "F4F6F9"
POSITIVE = "EAF7EF"
CAUTION = "FFF5E6"
RISK = "FDECEC"
TEAL = "0D8F8B"


def set_run(run, *, size=11, color=BLACK, bold=None, italic=False, font="Calibri"):
    run.font.name = font
    r_pr = run._element.get_or_add_rPr()
    r_pr.rFonts.set(qn("w:ascii"), font)
    r_pr.rFonts.set(qn("w:hAnsi"), font)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.bold = bold
    run.italic = italic


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    node = tc_pr.find(qn("w:shd"))
    if node is None:
        node = OxmlElement("w:shd")
        tc_pr.append(node)
    node.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths, indent=120):
    table.autofit = False
    total = sum(widths)
    tbl_pr = table._tbl.tblPr
    for tag, value in (("tblW", total), ("tblInd", indent)):
        node = tbl_pr.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tbl_pr.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        column = OxmlElement("w:gridCol")
        column.set(qn("w:w"), str(width))
        grid.append(column)
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for index, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths[index]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)


def mark_header_row(row):
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(repeat)


def add_table(doc, headers, rows, widths, *, font_size=9.2):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    mark_header_row(table.rows[0])
    for index, value in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = value
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shade(cell, LIGHT)
        for run in cell.paragraphs[0].runs:
            set_run(run, size=9.5, color=INK, bold=True)
    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        for index, value in enumerate(values):
            cell = cells[index]
            cell.text = str(value)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_index % 2:
                shade(cell, ALT_LIGHT)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs:
                    set_run(run, size=font_size)
    set_table_geometry(table, widths)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(0)
    return table


def add_callout(doc, title, body, *, fill=CALLOUT):
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    mark_header_row(table.rows[0])
    cell = table.cell(0, 0)
    shade(cell, fill)
    set_cell_margins(cell, 110, 145, 110, 145)
    set_run(cell.paragraphs[0].add_run(title.upper()), size=8.7, color=DARK_BLUE, bold=True)
    paragraph = cell.add_paragraph(body)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.05
    for run in paragraph.runs:
        set_run(run, size=9.4)
    set_table_geometry(table, [9360])
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(0)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run(paragraph.add_run("P&Pmis Construction AI  |  "), size=8, color=MUTED)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph.add_run()._r.append(begin)
    paragraph.add_run()._r.append(instruction)
    paragraph.add_run()._r.append(separate)
    display = paragraph.add_run()
    set_run(display, size=8, color=MUTED)
    display._r.append(text)
    paragraph.add_run()._r.append(end)


def add_bottom_rule(paragraph, color=BLUE, size=14):
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        p_pr.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)


def set_image_alt(inline_shape, description):
    doc_pr = inline_shape._inline.docPr
    doc_pr.set("descr", description)
    doc_pr.set("title", "P&Pmis Construction AI")


def configure_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10
    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 16, 8),
        ("Heading 2", 13, BLUE, 12, 6),
        ("Heading 3", 12, DARK_BLUE, 8, 4),
    ):
        style = doc.styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True


def add_title_page(doc):
    # Define both variants explicitly. LibreOffice otherwise renders even pages
    # without reserving the header band when page-break-before is present.
    doc.settings.odd_and_even_pages_header_footer = True
    section = doc.sections[0]
    for header in (section.header.paragraphs[0], section.even_page_header.paragraphs[0]):
        header.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_run(header.add_run("TECHNICAL REPORT · GATE 07I"), size=8.5, color=MUTED, bold=True)
        add_bottom_rule(header, color="D9E1E8", size=6)
    for footer in (section.footer.paragraphs[0], section.even_page_footer.paragraphs[0]):
        add_page_number(footer)

    if LOGO.exists():
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(8)
        picture = paragraph.add_run().add_picture(str(LOGO), width=Inches(0.72))
        set_image_alt(picture, "Logotipo de P&Pmis Construction AI")
    kicker = doc.add_paragraph()
    kicker.paragraph_format.space_after = Pt(4)
    set_run(kicker.add_run("INFORME TÉCNICO DE IMPLEMENTACIÓN"), size=10, color=TEAL, bold=True)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    title.paragraph_format.keep_with_next = True
    set_run(title.add_run("Gate 07I"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    set_run(
        subtitle.add_run("Portfolio Scenario Convergence & Recommendation"),
        size=15,
        color=DARK_BLUE,
        bold=True,
    )
    metadata = [
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha", "26 de agosto de 2026"),
        ("Repositorio", "pypmis-ia-sas · branch main"),
        ("Migración", "20260826_0048 (head)"),
        ("Estado", "IMPLEMENTADO Y VALIDADO"),
    ]
    for label, value in metadata:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        set_run(paragraph.add_run(f"{label}: "), size=10.5, color=INK, bold=True)
        set_run(paragraph.add_run(value), size=10.5)
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(10)
    rule.paragraph_format.space_after = Pt(14)
    add_bottom_rule(rule)
    add_callout(
        doc,
        "Resultado ejecutivo",
        "Gate 07I PASS · READY_FOR_INVESTMENT_GATE_PREPARATION · can_enter_fid=false. "
        "La salida es una recomendación formal de Portfolio; no es aprobación de inversión.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Resultado", "Evidencia"],
        [
            ("Backend / API", "PASS", "21 rutas; ETag, idempotencia y SecurityEvent"),
            ("PostgreSQL", "PASS", "105 pruebas; upgrade/downgrade/upgrade"),
            ("Frontend", "PASS", "30 pruebas; TypeScript; navegación USER/ADMIN"),
            ("Browser", "PASS", "Playwright Chromium USER/ADMIN/negative"),
            ("Localhost", "ACTIVE", "http://localhost:5173/app"),
        ],
        [1900, 1300, 6160],
        font_size=9.2,
    )
    doc.add_page_break()


def add_contents(doc):
    heading = doc.add_heading("Contenido y trazabilidad", level=1)
    heading.paragraph_format.space_before = Pt(0)
    chapters = [
        ("A", "Gobierno y contratos fuente", "Entregables 1–11"),
        ("B", "Dominio de convergencia", "Entregables 12–20"),
        ("C", "Lifecycle, evidencia y handoff", "Entregables 21–31"),
        ("D", "Experiencia, seguridad y API", "Entregables 32–39"),
        ("E", "Validación y cierre", "Entregables 40–50"),
    ]
    add_table(doc, ["Capítulo", "Alcance", "Cobertura"], chapters, [1100, 5200, 3060])
    add_callout(
        doc,
        "Lectura del informe",
        "Cada entregable requerido por el PROMPT 07I aparece una sola vez, numerado del 1 al 50. "
        "Las evidencias reportadas corresponden a pruebas ejecutadas en esta entrega.",
    )
    doc.add_page_break()


def add_architecture_summary(doc):
    doc.add_heading("Arquitectura de decisión implementada", level=1)
    add_table(
        doc,
        ["Entrada gobernada", "Gate 07I", "Salida controlada"],
        [
            (
                "Gate 07G · Budget Scenarios FROZEN/READY/current",
                "Pairing explícito; alineación; conflicto forced; factibilidad; comparación",
                "Recomendación formal + hashes + evidencia",
            ),
            (
                "Gate 07H · Resource Scenarios FROZEN/READY/current",
                "DRAFT → IN_REVIEW → RECOMMENDED",
                "READY_FOR_INVESTMENT_GATE_PREPARATION",
            ),
            (
                "Gate 07F · hashes compartidos, score/rank/risk read-only",
                "No optimizer · no source reopening · no third selection state",
                "can_enter_fid=false",
            ),
        ],
        [2850, 3580, 2930],
        font_size=8.8,
    )
    add_callout(
        doc,
        "Boundary",
        "Gate 07I termina en preparación del futuro Investment Gate. No crea Funds, FEL/PDRI, FID, "
        "Initialization, Activation, Execution ni ganador automático.",
        fill=CAUTION,
    )


def add_deliverables(doc):
    chapters = {
        1: "A. Gobierno y contratos fuente",
        12: "B. Dominio de convergencia",
        21: "C. Lifecycle, evidencia y handoff",
        32: "D. Experiencia, seguridad y API",
        40: "E. Validación y cierre",
    }
    for number, title, body, evidence in SECTIONS:
        if number in chapters:
            doc.add_heading(chapters[number], level=1)
        heading = doc.add_heading(f"{number}. {title}", level=2)
        heading.paragraph_format.keep_with_next = True
        paragraph = doc.add_paragraph(body)
        paragraph.paragraph_format.keep_together = True
        paragraph.paragraph_format.keep_with_next = True
        fill = POSITIVE if "PASS" in evidence or number == 50 else RISK if "riesgo" in title.lower() else CALLOUT
        add_callout(doc, "Evidencia / decisión", evidence, fill=fill)


def add_appendix(doc):
    doc.add_page_break()
    doc.add_heading("Anexo A · Inventario técnico", level=1)
    add_table(
        doc,
        ["Componente", "Implementación"],
        [
            ("Backend", "app/modules/portfolio_convergence/{models,schemas,service,router}.py"),
            ("Migración", "alembic/versions/20260826_0048_gate07i_portfolio_convergence.py"),
            ("Frontend", "src/features/portfolio-convergence/*"),
            ("Navegación", "applicationNavigation.ts + workspace_context/navigator.py"),
            ("Seguridad", "constants.py + permissions.py + SecurityEvent"),
            ("Tests", "unit, PostgreSQL, Vitest, AppFlow y Playwright"),
            ("ADR", "docs/49-adr-gate07i-portfolio-scenario-convergence.md"),
        ],
        [2000, 7360],
    )
    doc.add_heading("Anexo B · Matriz de validación", level=1)
    add_table(
        doc,
        ["Validación", "Resultado", "Conteo / nota"],
        [
            ("Gate 07I unit", "PASS", "4/4"),
            ("PostgreSQL + regression", "PASS", "105/105"),
            ("Frontend + AppFlow", "PASS", "30/30"),
            ("Playwright Chromium", "PASS", "1/1"),
            ("Migration cycle", "PASS", "0047 → 0048 → 0047 → 0048"),
            ("Ruff / TypeScript", "PASS", "0 errores"),
        ],
        [3400, 1400, 4560],
    )
    add_callout(
        doc,
        "STOP",
        "No iniciar Investment Decision/FID, Funds/Funding, FEL/PDRI, Initialization, Activation, "
        "Execution ni optimizer/AI winner sin un prompt explícito posterior.",
        fill=RISK,
    )


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    configure_styles(doc)
    add_title_page(doc)
    add_contents(doc)
    add_architecture_summary(doc)
    add_deliverables(doc)
    add_appendix(doc)

    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07I — Portfolio Scenario Convergence & Recommendation"
    properties.subject = "Implementación y validación técnica Gate 07I"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = "Gate 07I, Portfolio, Scenario Convergence, Recommendation, FID boundary"
    properties.comments = "Generated from verified repository evidence on 2026-08-26."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
