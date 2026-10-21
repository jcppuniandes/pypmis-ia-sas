"""Local source-parse observations only, not production SLA or load validation."""

import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from app.modules.scope_foundation.imports import parse_excel_source, parse_ifc_source


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    qa = root / "outputs/.qa/wave-o1ba-20261020"
    sources = [
        ("ifc_import_parse", qa / "fixtures/real-scope.ifc", parse_ifc_source),
        ("excel_staging_parse", root / "backend/tests/fixtures/scope-foundation-items.csv", parse_excel_source),
    ]
    observations = []
    for label, path, parser in sources:
        content = path.read_bytes()
        samples = []
        for _number in range(1, 6):
            started = perf_counter()
            result = parser(content, path.name)
            elapsed = round((perf_counter() - started) * 1000, 3)
            assert result["validation"]["can_accept"]
            samples.append(elapsed)
        observations.append(
            {
                "label": label,
                "source_file": str(path.relative_to(root)),
                "source_sha256": hashlib.sha256(content).hexdigest(),
                "samples_ms": samples,
                "n": len(samples),
                "min_ms": min(samples),
                "median_ms": statistics.median(samples),
                "max_ms": max(samples),
                "result": "PASS",
            }
        )
    output = {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "caveat": "Local Windows development fixture only. First parse can include engine import/cold initialization. Not a production SLA, capacity or load result.",
        "parser_source_sha256": hashlib.sha256(
            (root / "backend/app/modules/scope_foundation/imports.py").read_bytes()
        ).hexdigest(),
        "observations": observations,
    }
    (qa / "import-performance.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
