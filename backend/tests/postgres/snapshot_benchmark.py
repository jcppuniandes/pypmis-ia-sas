"""Gate 04H full-snapshot benchmark for disposable PostgreSQL."""

from __future__ import annotations

import csv
import json
import os
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_enterprise_structure_postgres_e2e import _seed_release, _service

from app.modules.enterprise_structure.schemas import (
    RevisionApprovalRequest,
    RevisionMoveRequest,
    RevisionPublishRequest,
    RevisionRecordCodePreviewRequest,
    RevisionRollbackRequest,
)

DATABASE_URL = os.environ["GATE04H_DATABASE_URL"]
if os.getenv("GATE04H_EPHEMERAL") != "true" or not DATABASE_URL.startswith("postgresql+"):
    raise RuntimeError("Snapshot benchmark requires disposable PostgreSQL and GATE04H_EPHEMERAL=true")

ARTIFACT_DIR = Path(os.getenv("GATE04H_ARTIFACT_DIR", "artifacts/enterprise_structure/gate04h"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _measure[T](operation: Callable[[], T]) -> tuple[T, float]:
    started = time.perf_counter()
    result = operation()
    return result, round((time.perf_counter() - started) * 1000, 3)


def _run_case(db: Session, node_count: int) -> dict[str, Any]:
    seeded = _seed_release(db, f"benchmark-{node_count}", node_count=node_count)
    editor = _service(db, seeded, "editor-a")
    approver = _service(db, seeded, "approver")
    publisher = _service(db, seeded, "publisher")
    source = seeded["release"]
    snapshot_size = len(json.dumps(source.snapshot_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    tracemalloc.start()
    transaction_started = time.perf_counter()
    draft, clone_ms = _measure(lambda: editor.create_revision(source.id))
    draft, load_draft_ms = _measure(lambda: editor.get_revision(draft.id))
    _, preview_ms = _measure(
        lambda: editor.record_code_preview(
            draft.id,
            RevisionRecordCodePreviewRequest(
                parent_key="BU-B",
                workspace_type_code="portfolio",
                workspace_key="PF-A",
            ),
        )
    )
    draft, move_ms = _measure(
        lambda: editor.move_workspace(
            draft.id,
            "PF-A",
            RevisionMoveRequest(new_parent_key="BU-B"),
            expected_version=draft.revision_version,
        )
    )
    validation, validate_ms = _measure(lambda: editor.validate_revision(draft.id))
    comparison, diff_ms = _measure(lambda: editor.compare_revision(draft.id))
    approved, approve_ms = _measure(
        lambda: approver.approve_revision(
            draft.id,
            RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=comparison.diff_hash),
        )
    )
    successor, publish_ms = _measure(
        lambda: publisher.publish_revision(
            draft.id,
            RevisionPublishRequest(draft_hash=approved.draft_hash, diff_hash=approved.diff_hash),
        )
    )
    _, rollback_ms = _measure(
        lambda: publisher.rollback_revision(
            successor.id,
            RevisionRollbackRequest(reason=f"Benchmark rollback {node_count}", confirm=True),
        )
    )
    transaction_ms = round((time.perf_counter() - transaction_started) * 1000, 3)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "nodes": node_count,
        "snapshot_size_bytes": snapshot_size,
        "clone_ms": clone_ms,
        "load_draft_ms": load_draft_ms,
        "record_code_preview_ms": preview_ms,
        "move_subtree_ms": move_ms,
        "validate_ms": validate_ms,
        "diff_ms": diff_ms,
        "approve_ms": approve_ms,
        "publish_ms": publish_ms,
        "rollback_ms": rollback_ms,
        "transaction_ms": transaction_ms,
        "peak_memory_bytes": peak_bytes,
    }


def main() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Snapshot benchmark refuses non-PostgreSQL databases")
    results: list[dict[str, Any]] = []
    try:
        with Session(engine) as db:
            for node_count in (100, 1_000, 10_000):
                results.append(_run_case(db, node_count))
    finally:
        engine.dispose()

    payload = {
        "status": "COMPLETE",
        "database": "ephemeral PostgreSQL",
        "storage_model": "full snapshot",
        "results": results,
        "decision": {
            "choice": "RETAIN_FULL_SNAPSHOT",
            "rationale": (
                "No threshold was invented before measurement. The complete 10k run provides the evidence "
                "for operational review; delta storage remains out of Gate 04H scope."
            ),
        },
    }
    (ARTIFACT_DIR / "snapshot_benchmark.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    fieldnames = list(results[0])
    with (ARTIFACT_DIR / "snapshot_benchmark.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
