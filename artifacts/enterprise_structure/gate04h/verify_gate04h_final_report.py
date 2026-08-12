from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from lxml import etree


ROOT = Path(r"C:\Users\Ricardo\Documents\GitHub\pypmis-ia-sas\artifacts\enterprise_structure\gate04h")
OUT = ROOT / "rendered_final"
PDF = OUT / "gate04h-final-word-qa.pdf"
DOCX = Path(
    r"C:\Users\Ricardo\Documents\P&P\P&Pmis Construction AI\Diseño\Resumen de Sprint"
    r"\Informe_Tecnico_PPMIS_Workspace_Revision_Manager_Gate04H_2026-08-12.docx"
)
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def rasterize() -> list[Path]:
    document = pdfium.PdfDocument(str(PDF))
    paths: list[Path] = []
    for index in range(len(document)):
        image = document[index].render(scale=160 / 72).to_pil().convert("RGB")
        path = OUT / f"page-{index + 1:02d}.png"
        image.save(path, optimize=True)
        paths.append(path)
    return paths


def contact_sheet(paths: list[Path]) -> Path:
    columns = 3
    width = 340
    label_height = 26
    thumbs: list[Image.Image] = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        height = round(image.height * width / image.width)
        thumbs.append(image.resize((width, height)))
    height = max(image.height for image in thumbs)
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width, rows * (height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(thumbs):
        x = (index % columns) * width
        y = (index // columns) * (height + label_height)
        draw.text((x + 8, y + 6), f"Página {index + 1}", fill="black")
        sheet.paste(image, (x, y + label_height))
    path = OUT / "contact-sheet.png"
    sheet.save(path, optimize=True)
    return path


def pdf_audit() -> dict:
    pages: list[dict] = []
    with pdfplumber.open(PDF) as document:
        for index, page in enumerate(document.pages, start=1):
            text = page.extract_text() or ""
            words = page.extract_words() or []
            edge = [
                word
                for word in words
                if word["x0"] < 3
                or word["x1"] > page.width - 3
                or word["top"] < 3
                or word["bottom"] > page.height - 3
            ]
            pages.append(
                {
                    "page": index,
                    "characters": len(text.strip()),
                    "words": len(words),
                    "blank": len(text.strip()) < 20,
                    "edge_violations": len(edge),
                    "first_line": next((line for line in text.splitlines() if line.strip()), ""),
                    "last_line": next((line for line in reversed(text.splitlines()) if line.strip()), ""),
                }
            )
    return {
        "page_count": len(pages),
        "blank_pages": [page["page"] for page in pages if page["blank"]],
        "edge_violations": sum(page["edge_violations"] for page in pages),
        "pages": pages,
    }


def docx_audit() -> dict:
    with ZipFile(DOCX) as archive:
        bad_member = archive.testzip()
        document = etree.fromstring(archive.read("word/document.xml"))
    tables = document.xpath(".//w:tbl", namespaces=NS)
    page_breaks = document.xpath('.//w:br[@w:type="page"]', namespaces=NS)
    text = "".join(document.xpath(".//w:t/text()", namespaces=NS))
    return {
        "zip_test": bad_member,
        "tables": len(tables),
        "manual_page_breaks": len(page_breaks),
        "text_characters": len(text),
        "final_state_present": "READY_FOR_PROJECT_CREATOR" in text,
        "stale_state_present": "HARDENING_REQUIRED" in text,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pages = rasterize()
    sheet = contact_sheet(pages)
    report = {
        "renderer": "Microsoft Word COM SaveAs2 PDF + pypdfium2",
        "official_renderer": "UNAVAILABLE_MISSING_LIBREOFFICE",
        "pdf": pdf_audit(),
        "docx": docx_audit(),
        "contact_sheet": str(sheet),
        "visual_review": "PENDING_MANUAL_INSPECTION",
    }
    (ROOT / "document_qa_final.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
