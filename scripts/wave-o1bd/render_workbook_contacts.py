"""Combine private rendered ranges for visual review without editing XLSX."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bd-20261104/workbook"
spec = importlib.util.spec_from_file_location(
    "progress_contacts", ROOT / "scripts/wave-o1a/render_workbook_contact_sheets.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.QA = QA


def main():
    renders = json.loads((QA / "render-manifest.json").read_text("utf-8"))
    sheets = json.loads((QA / "build-manifest.json").read_text("utf-8"))["sheets"]
    assert len(sheets) == 19
    assert {entry["sheet"] for entry in renders} == {entry["sheet"] for entry in sheets}
    assert len({entry["file"] for entry in renders}) == len(renders)
    for entry in renders:
        source = (QA / entry["file"]).resolve()
        assert source.is_relative_to(QA.resolve()) and source.is_file(), entry
    module.main()


if __name__ == "__main__":
    main()
