"""Read-only preservation proof. Never boot the app or run seed against live data."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/validation/wave-o1a-20261019"


def sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def capture() -> dict:
    with psycopg.connect(
        "host=127.0.0.1 port=5432 dbname=pypmis user=pypmis password=pypmis"
    ) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        row = connection.execute(
            "SELECT to_jsonb(p) FROM projects p WHERE id=14"
        ).fetchone()
        project = row[0] if row else None
        references = []
        keys = connection.execute("""
            SELECT kcu.table_name,kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name=tc.constraint_name AND ccu.constraint_schema=tc.constraint_schema
            WHERE tc.constraint_type='FOREIGN KEY' AND ccu.table_name='projects'
              AND ccu.column_name='id' AND tc.table_schema='public'
            ORDER BY kcu.table_name,kcu.column_name
        """).fetchall()
        for table, column in keys:
            values = connection.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) FROM {} t WHERE {}=%s ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table), sql.Identifier(column)),
                (14,),
            ).fetchall()
            references.append(
                {
                    "table": table,
                    "column": column,
                    "count": len(values),
                    "sha256": sha(values),
                }
            )
        canonical = connection.execute(
            "SELECT to_jsonb(w) FROM enterprise_workspaces w WHERE id=14"
        ).fetchone()
        connection.rollback()
    files = subprocess.check_output(
        ["git", "ls-files", "backend/app", "frontend/src", "backend/alembic"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    fingerprints = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in files
        if (ROOT / name).is_file()
    }
    identity = (
        {
            key: project.get(key)
            for key in (
                "id",
                "tenant_id",
                "code",
                "status",
                "external_key",
                "record_code",
                "version",
            )
        }
        if project
        else None
    )
    return {
        "database": "pypmis",
        "read_only": True,
        "legacy_project14": identity,
        "project14_row_sha256": sha(project),
        "project14_references": references,
        "canonical_id14_is_not_legacy_identity": True,
        "canonical_project14": {
            key: canonical[0].get(key)
            for key in (
                "id",
                "tenant_id",
                "code",
                "external_key",
                "record_code",
                "status",
                "version",
            )
        }
        if canonical
        else None,
        "canonical_id14_row_sha256": sha(canonical[0] if canonical else None),
        "product_source_sha256": fingerprints,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "identity-before", "after"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"preservation-{args.phase}.json"
    assert not target.exists(), "Preserve original proof"
    observation = capture()
    if args.phase == "after":
        before = json.loads(
            (OUT / "preservation-before.json").read_text(encoding="utf-8")
        )["observation"]
        assert before["project14_row_sha256"] == observation["project14_row_sha256"]
        before_refs = {row["table"]: row for row in before["project14_references"]}
        after_refs = {row["table"]: row for row in observation["project14_references"]}
        assert all(after_refs.get(table) == row for table, row in before_refs.items())
        assert (
            before["canonical_id14_row_sha256"]
            == observation["canonical_id14_row_sha256"]
        )
    target.write_text(
        json.dumps(
            {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "observation": observation,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "project14": observation["legacy_project14"],
                "row_sha256": observation["project14_row_sha256"],
                "fk_tables": len(observation["project14_references"]),
                "source_files": len(observation["product_source_sha256"]),
            }
        )
    )


if __name__ == "__main__":
    main()
