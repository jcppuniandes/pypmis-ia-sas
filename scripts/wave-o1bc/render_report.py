"""Current packaged renderer with native read-only Word export provenance."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "cost_renderer",
    ROOT / "scripts/operational-master-architecture/render_word_export.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = ROOT / "outputs/wave-o1bc-20261022"
module.QA = ROOT / "outputs/.qa/wave-o1bc-20261022"
module.RENDERER = Path(
    "C:/Users/Ricardo/.codex/plugins/cache/openai-primary-runtime/documents/26.1022.11436/skills/documents/render_docx.py"
)


if __name__ == "__main__":
    module.main()
