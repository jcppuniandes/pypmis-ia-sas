"""Isolated pure-kernel benchmarks; never connects to a runtime/test database."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import platform
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.qra_engine.calculation import (  # noqa: E402 - explicit standalone backend path bootstrap
    ENGINE_VERSION,
    calculate,
    engine_manifest,
)


def process_peak_rss() -> int | None:
    if sys.platform == "win32":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
        return None
    import resource

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def snapshot(kind, count):
    schedule_mode = kind == "SCHEDULE_QRA"
    inputs = []
    for index in range(count):
        milestone = schedule_mode and index == count - 1
        inputs.append(
            {
                "source_kind": "SCHEDULE" if schedule_mode else "COST",
                "source_item_ref": f"I{index:06d}",
                "base_value": 0 if milestone else 10,
                "mode": "DETERMINISTIC" if milestone else "UNCERTAIN",
                "range_type": "ABSOLUTE_RANGE",
                "distribution_family": None if milestone else "UNIFORM",
                "parameters": {},
                "values": {} if milestone else {"min": 9, "max": 11},
                "unit": "HOURS" if schedule_mode else "USD",
                "allow_negative": False,
                "input_type": "DURATION_UNCERTAINTY" if schedule_mode else "ESTIMATE_UNCERTAINTY",
                "risk_refs": [],
            }
        )
    result = {
        "analysis_type": kind,
        "inputs": inputs,
        "correlations": {"method": "NO_CORRELATION"},
        "policy": {
            "engine_version": ENGINE_VERSION,
            "supported_analysis_types": ["COST_QRA", "SCHEDULE_QRA"],
            "percentiles": [50, 80, 90],
            "histogram_bins": 20,
            "chunk_size": 256,
            "max_correlation_dimension": 1000,
            "schedule_method": "NORMALIZED_ELAPSED_TIME_V1",
            "convergence": {
                "enabled": True,
                "min_iterations": 1000,
                "relative_mean_standard_error_tolerance": 0.01,
            },
        },
        "cost": {
            "currency": "USD",
            "basis": "BASE_COST",
            "deterministic_reference": count * 10,
        },
    }
    if schedule_mode:
        result["schedule"] = {
            "activities": [
                {
                    "ref": item["source_item_ref"],
                    "duration_unit": "HOURS",
                    "calendar_ref": "BENCH-CAL",
                    "status": "NOT_STARTED",
                    "original_duration": item["base_value"],
                    "remaining_duration": item["base_value"],
                }
                for item in inputs
            ],
            "relationships": [
                {
                    "predecessor": inputs[i]["source_item_ref"],
                    "successor": inputs[i + 1]["source_item_ref"],
                    "type": "FS",
                    "lag": 0,
                    "lag_unit": "HOURS",
                }
                for i in range(count - 1)
            ],
            "calendars": [
                {
                    "source_id": "BENCH-CAL",
                    "definition": "Explicit approved normalized elapsed-time benchmark; not interpreted as work calendar",
                }
            ],
            "unit": "HOURS",
            "unit_seconds": 3600,
            "date_anchor": "2026-01-01T00:00:00+00:00",
            "milestone_refs": [inputs[-1]["source_item_ref"]],
        }
    return result


def benchmark(kind, count, iterations):
    frozen = snapshot(kind, count)
    callbacks = []
    tracemalloc.start()
    cpu_start, start = time.process_time(), time.perf_counter()
    result = calculate(frozen, 730145, iterations, lambda n: callbacks.append(n))
    wall, cpu = time.perf_counter() - start, time.process_time() - cpu_start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    expected = (count - int(kind == "SCHEDULE_QRA")) * 10
    if not math.isclose(result["summary"]["mean"], expected, rel_tol=0.002):
        raise AssertionError("Benchmark numerical sanity check failed")
    if callbacks[0] != 0 or callbacks[-1] != iterations:
        raise AssertionError("Benchmark progress visibility failed")
    return {
        "analysis_type": kind,
        "input_count": count,
        "iterations": iterations,
        "chunk_size": 256,
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "peak_traced_bytes": peak,
        "process_peak_rss_bytes": process_peak_rss(),
        "iterations_per_second": iterations / wall,
        "sampled_input_values_per_second": iterations * count / wall,
        "result_payload_bytes": len(json.dumps(result, sort_keys=True, allow_nan=False).encode()),
        "progress_callbacks": len(callbacks),
        "database_reads": 0,
        "database_writes": 0,
        "database_measurement_scope": "Pure kernel has no database imports or connections; worker persistence measured separately",
        "mean": result["summary"]["mean"],
        "convergence_status": result["convergence"]["status"],
        "numeric_sanity": "PASS",
        "production_sla": False,
        "memory_notes": "Tracemalloc includes tracked kernel arrays; process RSS is cumulative high-water including imported libraries and prior cases",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--large-iterations", type=int, default=2000)
    args = parser.parse_args()
    cases = [
        benchmark("COST_QRA", 1000, 10000),
        benchmark("SCHEDULE_QRA", 1000, 10000),
        benchmark("SCHEDULE_QRA", 10000, args.large_iterations),
    ]
    report = {
        "engine_manifest": engine_manifest(),
        "profiled_at_utc": datetime.now(UTC).isoformat(),
        "runtime": {"python_version": platform.python_version(), "platform": platform.platform()},
        "fixture_semantics": "Explicit NOT_STARTED activities; remaining duration equals base; chain FS with final zero-duration milestone",
        "cases": cases,
        "release_claim": "ISOLATED_SYNTHETIC_PROFILE_NOT_PRODUCTION_SLA",
    }
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        output = args.output.resolve()
        allowed = (ROOT / "outputs" / ".qa").resolve()
        if allowed not in output.parents or output.suffix != ".json":
            raise ValueError("Benchmark output must be JSON below repository outputs/.qa")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
