"""Clarify the CLOSE-2 date without editing the preceding O2B reports."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2c-20261113"
NAME = "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Technical_Report1.docx"
BASE = ROOT / "outputs/wave-o2b" / NAME
OUT = QA / "microclose-candidate" / NAME
EXPECTED = "3242d97e55f3d5ad5fb07defc59ab76a94fa7c39ae81c15bd90a1b11bf3ca909"


def main():
    assert sha256(BASE.read_bytes()).hexdigest() == EXPECTED
    original = Document(BASE)
    cover = original.paragraphs[2]
    assert "11 noviembre 2026" in cover.text
    cover.add_run("\nCorte final O2B.CLOSE-2: 12 noviembre 2026")
    prior_footer = original.sections[0].footer.paragraphs[0]
    assert prior_footer.runs and "11 noviembre 2026" in prior_footer.text
    for run in prior_footer.runs:
        if "11 noviembre 2026" in run.text:
            run.text = run.text.replace("11 noviembre 2026", "Corte final 12 noviembre 2026")
    binary = BytesIO()
    original.save(binary)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(BASE) as base, ZipFile(binary) as updated, ZipFile(OUT, "w") as out:
        for entry in base.infolist():
            source = updated if entry.filename in {"word/document.xml", "word/footer1.xml"} else base
            out.writestr(entry, source.read(entry.filename))
    before, after = Document(BASE), Document(OUT)
    assert [p.text for p in before.paragraphs[3:]] == [p.text for p in after.paragraphs[3:]]
    assert len(before.tables) == len(after.tables)
    print(OUT)


if __name__ == "__main__":
    main()
