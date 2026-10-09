"""Fallback visual QA renderer for simple report DOCX files on Windows.

The canonical render_docx.py remains the first choice. This fallback is used
only when its required LibreOffice executable is unavailable. It reads the
DOCX block order, reproduces headings, body text, lists and tables with
ReportLab, then rasterizes every PDF page for visual inspection.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from docx import Document
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from pdf2image import convert_from_path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(r"C:\Users\Ricardo\Documents\GitHub\pypmis-ia-sas")
POPPLER = Path(
    r"C:\Users\Ricardo\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin"
)


def blocks(document: Document):
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield DocxParagraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield DocxTable(child, document)


def safe(text: str) -> str:
    return html.escape(text).replace("\n", "<br/>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_path = Path(args.docx).resolve()
    output_dir = Path(args.output_dir).resolve()
    if ROOT not in input_path.parents or ROOT not in output_dir.parents:
        raise RuntimeError("QA renderer paths must stay inside the workspace")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "fallback-word-layout-qa.pdf"

    source = Document(input_path)
    header_text = " | ".join(
        text
        for section in source.sections
        for paragraph in section.header.paragraphs
        if (text := paragraph.text.strip())
    ) or "P&Pmis Construction AI"
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=11.2,
        textColor=colors.HexColor("#202A33"),
        spaceAfter=4,
    )
    title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.black,
        spaceAfter=8,
    )
    headings = {
        1: ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.black, spaceBefore=7, spaceAfter=5),
        2: ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=colors.black, spaceBefore=5, spaceAfter=3),
        3: ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.8, leading=12, textColor=colors.black, spaceBefore=4, spaceAfter=2),
    }
    list_style = ParagraphStyle("List", parent=normal, leftIndent=12, firstLineIndent=-7, bulletIndent=3)
    story = []
    logo = ROOT / "frontend" / "public" / "pypmis-construction-ai-logo.png"
    if logo.exists():
        image = Image(str(logo), width=0.82 * inch, height=0.82 * inch)
        image.hAlign = "CENTER"
        story.extend([image, Spacer(1, 4)])

    image_consumed = False
    for block in blocks(source):
        if isinstance(block, DocxParagraph):
            xml = block._p.xml
            if 'w:type="page"' in xml:
                story.append(PageBreak())
                continue
            text = block.text.strip()
            if not text:
                continue
            style_name = block.style.name if block.style else "Normal"
            if style_name == "Title":
                story.append(Paragraph(safe(text), title))
            elif style_name.startswith("Heading"):
                try:
                    level = int(style_name.split()[-1])
                except ValueError:
                    level = 2
                story.append(Paragraph(safe(text), headings.get(level, headings[3])))
            elif "List" in style_name:
                story.append(Paragraph("• " + safe(text), list_style))
            else:
                # Skip the first image-only placeholder; the logo is inserted above.
                if not image_consumed and "graphic" in xml:
                    image_consumed = True
                    continue
                story.append(Paragraph(safe(text), normal))
        else:
            data: list[list[Paragraph]] = []
            for row in block.rows:
                data.append([Paragraph(safe(cell.text.strip()), normal) for cell in row.cells])
            if not data:
                continue
            count = len(data[0])
            raw_widths = []
            for cell in block.rows[0].cells:
                width = cell.width.inches if cell.width else 1.0
                raw_widths.append(max(width, 0.3))
            total = sum(raw_widths) or float(count)
            column_widths = [7.14 * inch * width / total for width in raw_widths]
            rendered = Table(data, colWidths=column_widths, repeatRows=1, hAlign="LEFT")
            commands = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.6),
                ("LEADING", (0, 0), (-1, -1), 9.2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7DEE3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
            for row_number in range(1, len(data)):
                if row_number % 2 == 0:
                    commands.append(("BACKGROUND", (0, row_number), (-1, row_number), colors.HexColor("#F5F7F8")))
            rendered.setStyle(TableStyle(commands))
            story.extend([rendered, Spacer(1, 3)])

    page_width, page_height = letter
    frame = Frame(0.68 * inch, 0.62 * inch, page_width - 1.36 * inch, page_height - 1.34 * inch, id="normal")

    def decorate(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#53616B"))
        canvas.drawRightString(page_width - 0.68 * inch, page_height - 0.35 * inch, header_text)
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(page_width / 2, 0.32 * inch, f"Informe técnico controlado · Página {doc.page}")
        canvas.restoreState()

    pdf = BaseDocTemplate(str(pdf_path), pagesize=letter, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0)
    pdf.addPageTemplates(PageTemplate(id="letter", frames=[frame], onPage=decorate))
    pdf.build(story)

    for old in output_dir.glob("page-*.png"):
        old.unlink()
    images = convert_from_path(str(pdf_path), dpi=144, poppler_path=str(POPPLER))
    for index, image in enumerate(images, start=1):
        image.save(output_dir / f"page-{index}.png", "PNG")
    print(f"pdf={pdf_path} pages={len(images)}")


if __name__ == "__main__":
    main()
