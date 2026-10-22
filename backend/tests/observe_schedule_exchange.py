"""Observe actual parser/diff timings on committed synthetic P6 subset fixtures.

Run in the isolated wave container:
python -m tests.observe_schedule_exchange --output /artifacts/exchange-performance.json
No database, P6 connection, production SLA or full Primavera round-trip is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns

from app.modules.schedule_foundation import exchange


def observe(*, samples: int = 7) -> dict:
    if not 5 <= samples <= 100:
        raise ValueError("samples must be between 5 and 100")
    fixtures = Path(__file__).parent / "fixtures"
    xml = (fixtures / "schedule-foundation-p6.xml").read_bytes()
    xer = (fixtures / "schedule-foundation-p6.xer").read_bytes()
    original = exchange.parse_schedule_source(xml, "fixture.xml")["snapshot"]
    successor = deepcopy(original)
    successor["activities"][0]["remaining_duration"] = 5
    successor["project"]["data_date"] = "2026-10-27T08:00:00"

    def measurements(callback):
        # Explicit warm-up is not counted as one of the observed samples.
        callback()
        values = []
        for _ in range(samples):
            start = perf_counter_ns()
            callback()
            values.append(round((perf_counter_ns() - start) / 1_000_000, 6))
        return {
            "samples_ms": values,
            "sample_count": len(values),
            "minimum_ms": min(values),
            "median_ms": statistics.median(values),
            "maximum_ms": max(values),
            "p95_nearest_rank_ms": sorted(values)[-1],
        }

    return {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "parser_sha256": hashlib.sha256(Path(exchange.__file__).read_bytes()).hexdigest(),
        "fixtures": {
            "xml": {"bytes": len(xml), "sha256": hashlib.sha256(xml).hexdigest()},
            "xer": {"bytes": len(xer), "sha256": hashlib.sha256(xer).hexdigest()},
            "project_count": 1,
            "wbs_count": len(original["wbs"]),
            "activity_count": len(original["activities"]),
            "calendar_count": len(original["calendars"]),
            "relationship_count": len(original["relationships"]),
            "provenance": "synthetic handcrafted structural fixtures, not licensed P6 application exports",
        },
        "xml_parse": measurements(lambda: exchange.parse_schedule_source(xml, "fixture.xml")),
        "xer_parse": measurements(lambda: exchange.parse_schedule_source(xer, "fixture.xer")),
        "snapshot_diff": measurements(lambda: exchange.diff_schedule(original, successor)),
        "source_modified": False,
        "database_accessed": False,
        "production_sla": False,
        "p6_application_roundtrip_verified": False,
        "limitations": [
            "Tiny fixtures characterize local implementation only, not production-size throughput.",
            "No network, database persistence, browser rendering or Primavera application duration is measured.",
            "p95 nearest-rank is the maximum at seven samples and is not a population estimate.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    result = observe(samples=args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sample_count_per_operation": args.samples}))


if __name__ == "__main__":
    main()
