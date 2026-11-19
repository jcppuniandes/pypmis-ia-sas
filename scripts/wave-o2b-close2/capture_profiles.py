"""Bind published policy and configuration pins to the CLOSE-2 final evidence."""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime

from validate import HEAD, QA, ROOT, chromium, snapshot

CONTAINER = "pypmis-o2b-close-migration"
DATABASE = "o2b_close_consumers"
USER = "o2b_close_migration"
PORTS = {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5558"}]}
SUITES = {
    "progress-lineage": {"PROGRESS": 2},
    "forecast-sources": {"FORECAST": 4},
    "postgres": {"COST": 1, "FORECAST": 2, "PROGRESS": 5},
}
SQL = """
BEGIN TRANSACTION READ ONLY;
WITH pins AS (
    SELECT
        a.id, a.tenant_id, a.project_workspace_id, a.consumer, a.created_at,
        a.source_entity_type, a.source_entity_id, a.source_version, a.source_hash,
        a.consumer_status, a.source_package_id,
        a.source_snapshot->'consumer_profile' AS consumer_pin,
        p.configuration_id AS procurement_id, p.configuration_hash AS procurement_hash,
        c.kind AS consumer_kind, c.code AS consumer_code, c.revision AS consumer_revision,
        c.version AS consumer_config_version, c.content_hash AS consumer_config_hash,
        c.status AS consumer_config_status,
        s.kind AS procurement_kind, s.code AS procurement_code, s.revision AS procurement_revision,
        s.version AS procurement_config_version, s.content_hash AS procurement_config_hash,
        s.status AS procurement_config_status
    FROM operational_procurement_adoptions a
    LEFT JOIN procurement_packages p ON p.id = a.source_package_id
        AND p.tenant_id = a.tenant_id AND p.project_workspace_id = a.project_workspace_id
    LEFT JOIN admin_configurations c
        ON c.id::text = a.source_snapshot->'consumer_profile'->>'id' AND c.tenant_id = a.tenant_id
    LEFT JOIN admin_configurations s ON s.id = p.configuration_id AND s.tenant_id = a.tenant_id
    WHERE a.created_at >= (:'start_at'::timestamptz AT TIME ZONE 'UTC')
        AND a.created_at <= (:'end_at'::timestamptz AT TIME ZONE 'UTC')
)
SELECT json_build_object(
    'database', current_database(),
    'user', current_user,
    'read_only', current_setting('transaction_read_only'),
    'postgres_version', current_setting('server_version'),
    'alembic_head', (SELECT version_num FROM alembic_version),
    'adoptions', coalesce((SELECT json_agg(pins ORDER BY id) FROM pins), '[]'::json)
);
ROLLBACK;
"""


def load(file):
    return json.loads(file.read_text("utf-8-sig"))


def utc(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Evidence must use a timezone-qualified timestamp")
    return parsed.astimezone(UTC)


def docker(*args, input_text=None):
    return subprocess.check_output(
        ["docker", *args], cwd=ROOT, input=input_text, encoding="utf-8"
    ).strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_pin(row, prefix, pin, kind):
    require(
        row[f"{prefix}_kind"] == kind
        and row[f"{prefix}_config_status"] == "published"
        and row[f"{prefix}_revision"] == pin["revision"]
        and row[f"{prefix}_config_hash"] == pin["hash"]
        and re.fullmatch(r"[0-9a-f]{64}", pin["hash"]),
        f"Invalid published {prefix} pin for adoption {row['id']}",
    )
    return {
        **pin,
        "kind": row[f"{prefix}_kind"],
        "code": row[f"{prefix}_code"],
        "version": row[f"{prefix}_config_version"],
        "status": row[f"{prefix}_config_status"],
    }


def capture(attempt):
    freeze_path = QA / "release" / f"freeze-{attempt}.json"
    frozen = load(freeze_path)
    require(
        snapshot() == frozen["source"],
        "Source drift; refusing to attach profile evidence",
    )
    freeze_hash = chromium.digest(freeze_path)
    cutoff = utc(frozen["frozen_at_utc"])
    identity = json.loads(
        docker("inspect", "--format", "{{json .HostConfig.PortBindings}}", CONTAINER)
    )
    require(
        identity == PORTS,
        "Disposable PostgreSQL container does not match the loopback binding",
    )
    require(
        docker("inspect", "--format", "{{.State.Running}}", CONTAINER) == "true",
        "Start the dedicated container first",
    )
    output = QA / "release" / f"profiles-{attempt}.json"
    require(not output.exists(), "Refusing to overwrite an existing profile manifest")

    lanes = []
    for lane, domains in SUITES.items():
        folder = QA / lane / attempt
        proof_path = folder / "consumer-proof.json"
        proof = load(proof_path)
        started, finished = (
            utc(proof[name]) for name in ("started_at_utc", "finished_at_utc")
        )
        junit = folder / "junit.xml"
        junit_hash = chromium.digest(junit)
        require(
            proof["result"] == "PASS"
            and proof["git_commit"] == frozen["source"]["git_commit"]
            and proof["database"] == DATABASE
            and proof["alembic_head"] == HEAD
            and proof["freeze_sha256"] == freeze_hash
            and proof["source_unchanged"] is True
            and proof["evidence_sha256"]["junit.xml"] == junit_hash
            and cutoff <= started <= finished,
            f"Lane {lane} is not tied to the selected successful freeze",
        )
        data = json.loads(
            docker(
                "exec",
                "-i",
                CONTAINER,
                "psql",
                "-X",
                "-qAt",
                "-U",
                USER,
                "-d",
                DATABASE,
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                f"start_at={started.isoformat()}",
                "-v",
                f"end_at={finished.isoformat()}",
                "-f",
                "-",
                input_text=SQL,
            )
        )
        require(
            data["database"] == DATABASE
            and data["user"] == USER
            and data["read_only"] == "on"
            and data["alembic_head"] == HEAD
            and data["postgres_version"].startswith("16."),
            "Query did not execute in the expected read-only PostgreSQL environment",
        )
        require(
            {row["consumer"] for row in data["adoptions"]} == set(domains)
            and all(
                sum(row["consumer"] == kind for row in data["adoptions"]) == count
                for kind, count in domains.items()
            )
            and len(
                {
                    (row["tenant_id"], row["project_workspace_id"])
                    for row in data["adoptions"]
                }
            )
            == 1,
            f"Expected the dedicated synthetic tenant and exact decisions in {lane}",
        )
        adoptions = []
        for row in data["adoptions"]:
            require(
                row["project_workspace_id"] != 14 and row["tenant_id"] > 1,
                "The profile observer cannot include the protected project or tenant",
            )
            adoptions.append(
                {
                    key: row[key]
                    for key in (
                        "id",
                        "tenant_id",
                        "project_workspace_id",
                        "consumer",
                        "created_at",
                        "source_entity_type",
                        "source_entity_id",
                        "source_version",
                        "source_hash",
                        "consumer_status",
                        "source_package_id",
                    )
                }
                | {
                    "consumer_profile": verify_pin(
                        row,
                        "consumer",
                        row["consumer_pin"],
                        f"{row['consumer'].lower()}_profile",
                    ),
                    "procurement_configuration": verify_pin(
                        row,
                        "procurement",
                        {
                            "id": row["procurement_id"],
                            "revision": row["procurement_revision"],
                            "hash": row["procurement_hash"],
                        },
                        "procurement_profile",
                    ),
                }
            )
        lanes.append(
            {
                "lane": lane,
                "suite_started_at_utc": started.isoformat(),
                "suite_finished_at_utc": finished.isoformat(),
                "proof": proof_path.relative_to(QA).as_posix(),
                "proof_sha256": chromium.digest(proof_path),
                "junit": junit.relative_to(QA).as_posix(),
                "junit_sha256": junit_hash,
                "adoptions": adoptions,
            }
        )
    chromium.write(
        output,
        {
            "result": "PASS",
            "attempt": attempt,
            "database": DATABASE,
            "read_only": True,
            "git_commit": frozen["source"]["git_commit"],
            "alembic_head": HEAD,
            "freeze_sha256": freeze_hash,
            "freeze_utc": cutoff.isoformat(),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "lanes": lanes,
        },
    )
    print(f"{output} ({sum(len(lane['adoptions']) for lane in lanes)} decisions)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.attempt):
        parser.error("Invalid attempt")
    capture(args.attempt)


if __name__ == "__main__":
    main()
