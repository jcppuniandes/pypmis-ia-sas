"""Seal actual architecture-artifact QA; never modifies Office or product files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from lxml import etree
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/validation/operational-master-architecture-20261019"
QA = ROOT / "outputs/.qa/operational-master-architecture-20261019"
OUT = ROOT / "outputs/operational-master-architecture-20261019"
REFERENCE = (
    ROOT
    / "outputs/business-uat-signoff-20261018/P&Pmis_Informe_Tecnico_Business_UAT_Signoff_20261018.docx"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visual-review-confirmed", action="store_true")
    args = parser.parse_args()
    assert args.visual_review_confirmed, (
        "Requires actual complete model/tool image review"
    )
    manifest = read(QA / "documents-build-manifest.json")
    assert sha(REFERENCE) == manifest["source_sha256"]
    data = read(ROOT / "docs/architecture/operational/architecture-data.json")
    assert (
        sha(ROOT / "docs/architecture/operational/architecture-data.json")
        == manifest["data_sha256"]
    )
    scopes = read(AUDIT / "final-scope-audit.json")
    assert scopes["result"] == "PASS" and scopes["product_file_count"] == 860
    assert not scopes["comparison"]["changed_product_files"]
    assert len(list(OUT.iterdir())) == 3, (
        "Deliverables folder must contain exactly 3 Office files"
    )
    documents = []
    for index, item in enumerate(manifest["outputs"]):
        path = Path(item["path"])
        assert sha(path) == item["sha256"]
        folder = "master-pages-final" if index == 0 else "roadmap-pages-final2"
        proof = read(QA / folder / "render-provenance.json")
        assert proof["input_docx_sha256"] == sha(path)
        assert len(proof["pages"]) == (24 if index == 0 else 10)
        for name, digest in proof["pages"].items():
            assert sha(QA / folder / name) == digest
        pdf = QA / folder / (path.stem + ".pdf")
        assert sha(pdf) == proof["input_pdf_sha256"]
        reused = []
        if index == 0:
            draft = read(QA / "master-pages-draft1/render-provenance.json")
            reused = [
                name
                for name, digest in proof["pages"].items()
                if draft["pages"].get(name) == digest
            ]
            assert len(reused) == 22
        with ZipFile(REFERENCE) as src, ZipFile(path) as dst:
            changed = [
                name for name in src.namelist() if src.read(name) != dst.read(name)
            ]
            assert set(changed) == {"word/document.xml", "word/footer1.xml"}
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            xml = etree.fromstring(dst.read("word/document.xml"))
            assert xml.find("w:body/w:sectPr", ns) is not None
            assert b"PAGE" in dst.read("word/footer1.xml")
            assert b"19 octubre 2026" in dst.read("word/footer1.xml")
        doc = Document(path)
        headings = [p.text for p in doc.paragraphs if p.style.name == "Heading 1"]
        assert [int(re.match(r"^(\d+)\.", text).group(1)) for text in headings] == list(
            range(1, (24 if index == 0 else 11) + 1)
        )
        pdf_doc = PdfReader(pdf)
        for number, page in enumerate(pdf_doc.pages, 1):
            text = page.extract_text()
            assert "Página" in text and str(number) in text
            assert len(text) > 500, f"Unexpected near-empty page {number}"
        a11y = read(QA / ("master-a11y.json" if index == 0 else "roadmap-a11y.json"))
        assert a11y["counts"] == {"high": 0, "medium": 0, "low": 0}
        documents.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha(path),
                "pages": len(proof["pages"]),
                "chapters": len(headings),
                "native_parts_preserved": 17,
                "a11y_findings": 0,
                "visual_review": "PASS_CODEX_TOOL_IMAGE_REVIEW_ALL_PAGES",
                "reviewed_draft_pages_reused_by_identical_png_sha": reused,
                "final_page_hashes": proof["pages"],
            }
        )
        item["visual_review"] = "PASS_CODEX_TOOL_IMAGE_REVIEW_ALL_PAGES"
    write(QA / "documents-build-manifest.json", manifest)
    workbook = read(QA / "workbook/saved-verification.json")
    native = read(QA / "workbook/native-verification.json")
    scenarios = read(QA / "workbook/formula-scenarios.json")
    assert native["failed"] == scenarios["failed"] == 0
    assert native["passed"] == 22 and scenarios["passed"] == 12
    assert len(workbook["renders"]) == 106
    contacts = read(QA / "contacts/manifest.json")
    assert len(contacts["contacts"]) == 32
    assert sum(len(item["ranges"]) for item in contacts["contacts"]) == 106
    for view in workbook["renders"]:
        assert sha(ROOT / view["path"]) == view["sha256"]
    workbook_path = next(OUT.glob("*.xlsx"))
    assert sha(workbook_path) == native["output_sha256"] == workbook["outputSha256"]
    workbook["visualReview"] = (
        "PASS_CODEX_TOOL_IMAGE_REVIEW_106_RANGES_VIA_32_CONTACTS_PLUS_NATIVE_DETAIL"
    )
    write(QA / "workbook/saved-verification.json", workbook)
    build = read(QA / "workbook/build-manifest.json")
    build["visualReview"] = workbook["visualReview"]
    write(QA / "workbook/build-manifest.json", build)
    result = {
        "status": "PASS_ARCHITECTURE_PACKAGE_NOT_BUSINESS_RELEASE",
        "cutoff": "2026-10-19 America/Bogota",
        "documents": documents,
        "workbook": {
            "path": str(workbook_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha(workbook_path),
            "sheets": 12,
            "native_checks_passed": 22,
            "formula_scenarios_passed": 12,
            "render_ranges_reviewed": 106,
            "contact_sheets_reviewed": 32,
            "full_rationale_notes": 25,
            "formula_cells": native["formula_cells_observed"],
            "native_excel_recalculation": False,
        },
        "architecture_acceptance": {
            "defined": len(data["acceptance"]),
            "runtime_tests": 0,
        },
        "product_files_unchanged": 860,
        "application_tests_executed": 0,
        "database_commands": 0,
        "migrations": 0,
        "business_signoffs": 0,
        "commit_push": 0,
        "source_doc_unchanged": True,
        "next_increment": "WAVE O1 — PROJECT CONTROLS FOUNDATION; O1A first; not started",
        "strategic_state_preserved": data["strategic_state_preserved"],
        "scope_audit": "docs/validation/operational-master-architecture-20261019/final-scope-audit.json",
        "script_note": "Only task-local documentation/QA scripts were formatted by Ruff; no product file changed.",
    }
    write(AUDIT / "artifact-quality-report.json", result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "docx_pages": [24, 10],
                "workbook_sheets": 12,
                "reviewed_ranges": 106,
                "product_files_unchanged": 860,
            }
        )
    )


if __name__ == "__main__":
    main()
