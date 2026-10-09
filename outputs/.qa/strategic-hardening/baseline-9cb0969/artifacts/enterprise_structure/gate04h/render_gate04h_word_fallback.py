from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from lxml import etree


ROOT = Path(r"C:\Users\Ricardo\Documents\GitHub\pypmis-ia-sas\artifacts\enterprise_structure\gate04h")
PDF = ROOT / "rendered" / "gate04h-word-qa.pdf"
DOCX = Path(
    r"C:\Users\Ricardo\Documents\P&P\P&Pmis Construction AI\Diseño\Resumen de Sprint"
    r"\Informe_Tecnico_PPMIS_Workspace_Revision_Manager_Gate04H_2026-08-10.docx"
)
OUT = ROOT / "rendered"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def rasterize() -> list[Path]:
    document = pdfium.PdfDocument(str(PDF))
    paths: list[Path] = []
    scale = 160 / 72
    for index in range(len(document)):
        bitmap = document[index].render(scale=scale)
        image = bitmap.to_pil().convert("RGB")
        path = OUT / f"page-{index + 1:02d}.png"
        image.save(path, optimize=True)
        paths.append(path)
    return paths


def contact_sheet(paths: list[Path]) -> None:
    columns = 3
    thumb_width = 300
    label_height = 28
    thumbs: list[Image.Image] = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        height = round(image.height * thumb_width / image.width)
        thumbs.append(image.resize((thumb_width, height)))
    thumb_height = max(image.height for image in thumbs)
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(thumbs):
        x = (index % columns) * thumb_width
        y = (index // columns) * (thumb_height + label_height)
        sheet.paste(image, (x, y + label_height))
        draw.text((x + 8, y + 7), f"Page {index + 1}", fill="black")
    sheet.save(OUT / "contact-sheet.png", optimize=True)


def pdf_audit() -> dict:
    pages = []
    with pdfplumber.open(PDF) as document:
        for index, page in enumerate(document.pages, start=1):
            words = page.extract_words() or []
            text = page.extract_text() or ""
            edge_violations = [
                word
                for word in words
                if word["x0"] < 4
                or word["x1"] > page.width - 4
                or word["top"] < 4
                or word["bottom"] > page.height - 4
            ]
            pages.append(
                {
                    "page": index,
                    "characters": len(text.strip()),
                    "words": len(words),
                    "blank": len(text.strip()) < 20,
                    "edge_violations": len(edge_violations),
                }
            )
    return {
        "pages": pages,
        "page_count": len(pages),
        "blank_pages": [item["page"] for item in pages if item["blank"]],
        "edge_violations": sum(item["edge_violations"] for item in pages),
    }


def docx_audit() -> dict:
    with ZipFile(DOCX) as archive:
        document_xml = etree.fromstring(archive.read("word/document.xml"))
        styles_xml = etree.fromstring(archive.read("word/styles.xml"))
    tables = document_xml.xpath(".//w:tbl", namespaces=NS)
    table_results = []
    for index, table in enumerate(tables, start=1):
        grid = [int(node.get(f"{{{NS['w']}}}w")) for node in table.xpath("./w:tblGrid/w:gridCol", namespaces=NS)]
        width_nodes = table.xpath("./w:tblPr/w:tblW", namespaces=NS)
        indent_nodes = table.xpath("./w:tblPr/w:tblInd", namespaces=NS)
        table_results.append(
            {
                "table": index,
                "grid_sum": sum(grid),
                "table_width": int(width_nodes[0].get(f"{{{NS['w']}}}w")) if width_nodes else None,
                "table_indent": int(indent_nodes[0].get(f"{{{NS['w']}}}w")) if indent_nodes else None,
                "fixed_geometry": sum(grid) == 9360,
            }
        )
    section = document_xml.xpath(".//w:sectPr[last()]", namespaces=NS)[0]
    margins = section.xpath("./w:pgMar", namespaces=NS)[0]
    style_names = {
        node.get(f"{{{NS['w']}}}styleId")
        for node in styles_xml.xpath(".//w:style", namespaces=NS)
    }
    return {
        "tables": table_results,
        "table_count": len(tables),
        "all_tables_fixed_9360": all(item["fixed_geometry"] for item in table_results),
        "all_table_indents_120": all(item["table_indent"] == 120 for item in table_results),
        "page_margins_dxa": {
            key: int(margins.get(f"{{{NS['w']}}}{key}")) for key in ("top", "right", "bottom", "left")
        },
        "required_styles_present": all(
            style in style_names for style in ("Normal", "Heading1", "Heading2", "Heading3", "ListBullet", "ListNumber")
        ),
    }


def main() -> None:
    paths = rasterize()
    contact_sheet(paths)
    report = {
        "renderer": "Microsoft Word COM to PDF + pypdfium2",
        "official_renderer": "FAILED_MISSING_LIBREOFFICE",
        "pdf": pdf_audit(),
        "docx": docx_audit(),
        "visual_review": "PENDING_MANUAL_INSPECTION",
    }
    (ROOT / "document_qa.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
