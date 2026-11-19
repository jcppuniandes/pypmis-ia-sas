"""Observe Project 14 without applying migrations, bootstrapping, or seeding it."""

import argparse
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/.qa/wave-o2c-20261118/project-14"


def capture():
    spec = importlib.util.spec_from_file_location(
        "upstream_preservation", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    upstream = observer.capture()
    result = {
        key: upstream[key]
        for key in (
            "legacy_project14",
            "project14_row_sha256",
            "project14_references",
            "canonical_project14",
            "canonical_id14_row_sha256",
        )
    }
    with psycopg.connect(
        "host=127.0.0.1 port=5432 dbname=pypmis user=pypmis password=pypmis"
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        keys = connection.execute("""
            SELECT DISTINCT t.relname, a.attname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            CROSS JOIN LATERAL unnest(c.conkey) AS k(attnum)
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
            WHERE c.contype = 'f' AND c.confrelid = 'public.enterprise_workspaces'::regclass
              AND n.nspname = 'public' AND cardinality(c.conkey) = 1
            ORDER BY 1, 2
        """).fetchall()
        references = []
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
                    "sha256": observer.sha(values),
                }
            )
        result["canonical_workspace14_references"] = references
        connection.rollback()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    phase = parser.parse_args().phase
    OUT.mkdir(parents=True, exist_ok=True)
    result = capture()
    if phase == "after":
        before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))
        if before["observation"] != result:
            raise RuntimeError("Project 14 data or referencing catalog changed")
    target = OUT / f"preservation-{phase}.json"
    with target.open("x", encoding="utf-8") as output:
        json.dump(
            {
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "read_only": True,
                "observation": result,
            },
            output,
            indent=2,
        )
    print(
        f"{phase}: {len(result['project14_references'])} legacy and "
        f"{len(result['canonical_workspace14_references'])} workspace reference checks (read-only)"
    )


if __name__ == "__main__":
    main()
