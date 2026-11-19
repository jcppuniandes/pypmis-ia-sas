"""Extract only the final consumer JUnit cases and synthetic policy identities."""

import json
import subprocess
import sys
from datetime import datetime
from hashlib import sha256
from xml.etree import ElementTree

from closeout_evidence import cases, load, passed
from freeze import HEAD, QA

CONTAINER = "pypmis-o2b-close-migration"
DATABASE = "o2b_close_consumers"
USER = "o2b_close_migration"
DOMAINS = ("cost", "progress", "forecast")


def record(attempt):
    original = QA / "postgres" / f"consumer-{attempt}" / "junit.xml"
    assert passed(cases(original), 7)
    freeze = load(QA / "release" / f"freeze-{attempt}.json")
    started = datetime.fromisoformat(freeze["frozen_at_utc"]).isoformat()
    command = [
        "docker",
        "exec",
        CONTAINER,
        "psql",
        "-X",
        "-qAt",
        "--set",
        "ON_ERROR_STOP=1",
        "-U",
        USER,
        "-d",
        DATABASE,
    ]
    sql = f"""
        BEGIN TRANSACTION READ ONLY;
        SELECT json_build_object(
            'database', current_database(),
            'read_only', current_setting('transaction_read_only'),
            'head', (SELECT version_num FROM alembic_version),
            'profiles', coalesce(json_agg(q ORDER BY q.consumer), '[]'::json)
        )
        FROM (
            SELECT DISTINCT ON (a.consumer)
                a.consumer, a.tenant_id, a.project_workspace_id,
                c.id, c.kind, c.code, c.version, c.revision, c.status, c.content_hash
            FROM operational_procurement_adoptions a
            JOIN admin_configurations c
                ON c.id = (a.source_snapshot->'consumer_profile'->>'id')::integer
                AND c.tenant_id = a.tenant_id
                AND c.content_hash = a.source_snapshot->'consumer_profile'->>'hash'
            WHERE a.created_at >= (TIMESTAMPTZ '{started}' AT TIME ZONE 'UTC')
            ORDER BY a.consumer, a.id DESC
        ) q;
        ROLLBACK;
    """
    profiles = json.loads(
        subprocess.check_output([*command, "-c", sql], encoding="utf-8")
    )
    assert (
        profiles["database"] == DATABASE
        and profiles["head"] == HEAD
        and profiles["read_only"] == "on"
    )
    assert {row["consumer"].lower() for row in profiles["profiles"]} == set(DOMAINS)
    assert all(row["status"] == "published" for row in profiles["profiles"])
    profiles["attempt"] = attempt
    profiles["junit_sha256"] = sha256(original.read_bytes()).hexdigest()
    target = original.parent / "profile-proof.json"
    target.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), "utf-8")
    selections = {
        **{
            f"consumer-{name}": f"test_procurement_{name}_consumer_release"
            for name in DOMAINS
        },
        "regression/integration-policies": "test_procurement_consumer_sources",
    }
    for name, match in selections.items():
        rows = cases(original, match)
        assert len(rows) == (4 if "policies" in name else 1) and passed(rows)
        suite = ElementTree.Element(
            "testsuite",
            name=name,
            tests=str(len(rows)),
            failures="0",
            errors="0",
            skipped="0",
        )
        properties = ElementTree.SubElement(suite, "properties")
        ElementTree.SubElement(
            properties,
            "property",
            name="original_sha256",
            value=profiles["junit_sha256"],
        )
        suite.extend(rows)
        path = QA / name / attempt / "junit.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        ElementTree.ElementTree(suite).write(
            path, encoding="utf-8", xml_declaration=True
        )
    print(target)


if __name__ == "__main__":
    record(sys.argv[1])
