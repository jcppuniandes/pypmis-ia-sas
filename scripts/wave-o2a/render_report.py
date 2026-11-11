"""Use the same native Word export bridge and packaged renderer as O1C."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "o2a_bridge", ROOT / "scripts/wave-o1c/render_report.py"
)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
bridge.module.OUT = ROOT / "outputs/wave-o2a-20261109"
bridge.module.QA = ROOT / "outputs/.qa/wave-o2a-20261109"

if __name__ == "__main__":
    bridge.module.main()
