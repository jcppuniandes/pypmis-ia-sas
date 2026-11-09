"""Read-only retained report inventory and task-local Word slot contract."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106"
REFERENCE = (
    ROOT
    / "outputs/wave-o1bd-20261104/P&Pmis_Wave_O1B_D_Progress_and_Baseline_Integration_Technical_Report.docx"
)
SHA = "ea1934490194120ed7d6ae6045145e12b4e219dfb5d41816cf6b4e33f670e0a0"
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
                "source_pages": 8,
                "sections": sections,
                "styles": roles,
                "parts": inventory,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    contract = (ROOT / "scripts/wave-o1c/TEMPLATE_CONTRACT.md").read_text("utf-8")
    (QA / "artifact.md").write_text(contract, encoding="utf-8")
    print(
        json.dumps(
            {"reference_sha": SHA, "parts": len(inventory), "source_pages_reviewed": 8}
        )
    )


if __name__ == "__main__":
    main()
