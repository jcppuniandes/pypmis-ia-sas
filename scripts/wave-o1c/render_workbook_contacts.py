"""Compose private contact sheets from the verified O1C preview inventory."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106/workbook"
SPEC = importlib.util.spec_from_file_location(
    "o1c_contacts", ROOT / "scripts/wave-o1a/render_workbook_contact_sheets.py"
)


def main():
    previews = json.loads((QA / "render-manifest.json").read_text("utf-8"))
    sheets = json.loads((QA / "build-manifest.json").read_text("utf-8"))["sheets"]
    assert len(sheets) == 19
    assert {entry["sheet"] for entry in previews} == {
        entry["sheet"] for entry in sheets
    }
    assert len({entry["file"] for entry in previews}) == len(previews)
    for entry in previews:
        source = (QA / entry["file"]).resolve()
        assert source.is_relative_to(QA.resolve()) and source.is_file(), entry
    contacts = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(contacts)
    contacts.QA = QA
    contacts.main()


if __name__ == "__main__":
    main()
