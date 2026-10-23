"""Reuse validated contact-sheet layout for Cost's private rendered ranges.

This combines existing PNGs only. It does not open, recalculate or edit XLSX.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bc-20261022/workbook"
spec = importlib.util.spec_from_file_location(
    "cost_contacts", ROOT / "scripts/wave-o1a/render_workbook_contact_sheets.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.QA = QA


def main():
    renders = json.loads((QA / "render-manifest.json").read_text("utf-8"))
    sheets = json.loads((QA / "build-manifest.json").read_text("utf-8"))["sheets"]
    assert len(sheets) == 18, "Exactly eighteen Cost traceability sheets required"
    assert {entry["sheet"] for entry in renders} == {entry["sheet"] for entry in sheets}
    assert len({entry["file"] for entry in renders}) == len(renders)
    for entry in renders:
        source = (QA / entry["file"]).resolve()
        assert source.is_relative_to(QA.resolve()) and source.is_file(), entry
    module.main()


if __name__ == "__main__":
    main()
