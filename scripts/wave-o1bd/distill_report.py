"""Read-only retained report inventory and task-local Word slot contract."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bd-20261104"
REFERENCE = (
    ROOT
    / "outputs/wave-o1bc-20261022/P&Pmis_Wave_O1B_C_Cost_Foundation_Technical_Report.docx"
)
SHA = "76f508eb7073c15a52c1f648abe1e89b284ace20858c634d443792f9e169da77"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def main():
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == SHA
    with ZipFile(REFERENCE) as z:
        body = ET.fromstring(z.read("word/document.xml"))
        styles = ET.fromstring(z.read("word/styles.xml"))
        sections = [
            ET.tostring(n, encoding="unicode") for n in body.findall(".//w:sectPr", NS)
        ]
        roles = {
            n.get("{" + NS["w"] + "}styleId"): ET.tostring(n, encoding="unicode")
            for n in styles.findall("w:style", NS)
            if n.get("{" + NS["w"] + "}styleId")
            in {"Normal", "Title", "Subtitle", "Heading1"}
        }
        inventory = [
            {
                "part": n,
                "bytes": len(z.read(n)),
                "sha256": hashlib.sha256(z.read(n)).hexdigest(),
                "policy": "editable body"
                if n == "word/document.xml"
                else "literal date only"
                if n == "word/footer1.xml"
                else "semantic title subject keywords description and timestamps"
                if n == "docProps/core.xml"
                else "preserve byte for byte",
            }
            for n in z.namelist()
        ]
    assert len(sections) == 1
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "template-evidence.json").write_text(
        json.dumps(
            {
                "reference": str(REFERENCE),
                "sha256": SHA,
                "source_pages": 7,
                "sections": sections,
                "styles": roles,
                "parts": inventory,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    contract = f"""# Progress report retained template contract

Reference {REFERENCE.as_posix()}
SHA256 {SHA}. Retained reference unchanged. Seven pages, one section.
Source render outputs/.qa/wave-o1bc-20261022/word-pages-v1/page-1.png through page-7.png.
All seven full-size source pages reviewed in this task. Native source export hash and package audit retained.

## Page and components
Letter portrait 8.5 by 11 inches. All margins approximately0.7201 inches, exact sectPr in template-evidence.json.
One section, continuous body flow. Native Aptos Normal11, black Title24, italic Subtitle12, black Heading1 15.
Exact spacing, line height, keeps, tabs and source roles retained in template-evidence.json style XML.
Source logo first body paragraph retained with relationship and drawing unchanged.
Source footer native PAGE field, right aligned date then Página and page number.
Tables clone source navy header white text, pale blue alternating rows, light gray borders, repeated header, flexible heights.
Body functions reuse retained component functions and widths; never shrink font to fit.

## Ordered content and slots
word/document.xml /w:document/w:body first paragraph logo preserve only.
Title and Subtitle after logo replace with O1B D progress subject and 5 noviembre2026.
Remaining body paragraphs and tables replace with 39 numbered requested chapters and executed validation evidence.
Heading1 and Normal native patterns may repeat for new chapters. Tables may repeat the validated source grid pattern.
No source Cost business results are carried forward as new Progress results.
Final w:sectPr preserve exactly. No extra section or unsupported page geometry changes.
word/footer1.xml date text23 octubre2026 replace only with5 noviembre2026. Preserve PAGE field and formatting.
No text boxes or editable SDTs used. All text outside body and literal footer date preserve only.
docProps/core.xml title subject keywords description and timestamps replace with the actual Progress report identity and creation time. Preserve creator and other fields. The retained source has stale Gate07J metadata which must not describe this report.
All other ZIP members and relationships preserve byte for byte, including styles, numbering, image and settings.
Part SHA and policy inventory in template-evidence.json is authoritative.

## Fidelity gates
Report generator must reject reference SHA mismatch and compare package members after output.
Only document body, literal footer date and declared semantic core metadata slots may change. Exact section XML, logo, relationships, styles and image bytes remain.
Use native read-only Word PDF export for PAGE pagination, then current packaged render_docx.py via provenance bridge.
Inspect every final full-size page. Verify all39 headings, no leftover Cost result claims, no placeholder counts and no invented release PASS.
Native OOXML relationship, CRC, heading and accessibility audits are separate from visual review.
"""
    (QA / "artifact.md").write_text(contract, encoding="utf-8")
    print(
        json.dumps(
            {"reference_sha": SHA, "parts": len(inventory), "source_pages_reviewed": 7}
        )
    )


if __name__ == "__main__":
    main()
