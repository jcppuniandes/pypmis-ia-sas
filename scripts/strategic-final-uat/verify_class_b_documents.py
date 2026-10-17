"""Read-only fidelity checks for the blocked Gate07J report successors."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/strategic-uat-remediation-20261015"
OUT = ROOT / "outputs/gate07j-controlled-class-b-20261015"
DATA = ROOT / "docs/validation/gate07j-controlled-class-b"
QA = ROOT / "outputs/.qa/gate07j-controlled-class-b"
PREFIX = "P&Pmis_Strategic_Macroprocess_"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(path):
    with Image.open(path) as image:
        return image.size, hashlib.sha256(image.tobytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--visual-reviewed", action="store_true")
    args = parser.parse_args()
    previous = json.loads(
        (
            ROOT
            / "docs/validation/strategic-uat-remediation/artifact-structural-verification.json"
        ).read_text()
    )
    for artifact in previous["artifacts"]:
        assert sha(SOURCE / artifact["name"]) == artifact["sha256"]
    result = []
    for suffix, kind in (
        ("Final_Release_Closeout", "closeout"),
        ("UAT_Plan_and_Results", "uat"),
    ):
        name = PREFIX + suffix + ".docx"
        with ZipFile(SOURCE / name) as before, ZipFile(OUT / name) as after:
            assert after.testzip() is None
            assert before.namelist() == after.namelist()
            changed = [
                part
                for part in before.namelist()
                if before.read(part) != after.read(part)
            ]
            assert set(changed) <= {"word/document.xml", "docProps/core.xml"}, changed
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            old_body = etree.fromstring(before.read("word/document.xml")).find(
                "w:body", ns
            )
            new_body = etree.fromstring(after.read("word/document.xml")).find(
                "w:body", ns
            )
            assert etree.tostring(old_body[-1]) == etree.tostring(new_body[-1])
            if kind == "uat":
                for index, element in enumerate(old_body[:-1]):
                    assert etree.tostring(element) == etree.tostring(new_body[index])
        pages = list((QA / f"word-{kind}" / "pages-final").glob("page-*.png"))
        assert len(pages) == (6 if kind == "closeout" else 37)
        retained = 0
        if kind == "uat":
            for number in range(1, 37):
                previous_page = (
                    ROOT
                    / f"outputs/.qa/strategic-uat-remediation/word-UAT_Plan_and_Results/pages-final/page-{number}.png"
                )
                current_page = QA / f"word-uat/pages-final/page-{number}.png"
                assert pixels(previous_page) == pixels(current_page), number
                retained += 1
        else:
            headings = [
                p.text
                for p in Document(OUT / name).paragraphs
                if p.style.name == "Heading 1"
            ]
            assert len(headings) == 34
        a11y = json.loads((QA / f"word-{kind}/a11y.json").read_text())
        assert not any(a11y["counts"].values())
        result.append(
            {
                "file": str(OUT / name),
                "sha256": sha(OUT / name),
                "pages": len(pages),
                "retained_pages_pixel_identical": retained,
                "changed_parts": changed,
                "a11y": a11y["counts"],
            }
        )
    preflight = json.loads((DATA / "preflight.json").read_text(encoding="utf-8"))
    assert preflight["status"] == "BLOCKED_UAT_DATABASE_NOT_AVAILABLE"
    assert preflight["commands_against_selected_chain"] == 0
    assert preflight["current_tests"]["counts"] is None
    assert preflight["current_browser"]["counts"] is None
    assert json.loads((DATA / "operational-before.json").read_text()) == json.loads(
        (DATA / "operational-after.json").read_text()
    )
    requirements = json.loads((DATA / "requirement-reconciliation.json").read_text())
    assert len(requirements) == 19
    assert all(
        r["currentness"] == "NOT_VERIFIABLE" and r["current_coverage"] is None
        for r in requirements
    )
    final = {
        "release": "STRATEGIC_MACROPROCESS_NOT_VALIDATED",
        "decision": "NO_GO",
        "artifacts": result,
        "operational_preservation": "READ_ONLY_BEFORE_AFTER_IDENTICAL",
        "visual_review": "PASS_ROOT_REVIEW_OF_ALL_NEW_PAGES"
        if args.visual_reviewed
        else "PENDING_ROOT_REVIEW",
    }
    (DATA / "document-verification.json").write_text(
        json.dumps(final, indent=2), encoding="utf-8"
    )
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
