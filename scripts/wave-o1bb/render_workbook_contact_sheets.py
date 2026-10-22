"""Reuse the reviewed O1A contact layout for private Schedule workbook QA."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "scope_contacts", ROOT / "scripts/wave-o1a/render_workbook_contact_sheets.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.QA = ROOT / "outputs/.qa/wave-o1bb-20261020/workbook"

if __name__ == "__main__":
    module.main()
