"""Assemble contact sheets for all O2A workbook preview ranges."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "o2a_workbook_contacts", ROOT / "scripts/wave-o1a/render_workbook_contact_sheets.py"
)
assert SPEC and SPEC.loader
contacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contacts)
contacts.QA = ROOT / "outputs/.qa/wave-o2a-20261109/workbook"

if __name__ == "__main__":
    contacts.main()
