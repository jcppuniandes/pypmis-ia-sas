"""Read-only operational preservation check; never provisions or migrates data."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs/validation/strategic-uat-remediation"
SQL = """
BEGIN READ ONLY;
SELECT jsonb_build_object(
 'workspace_count', (SELECT count(*) FROM enterprise_workspaces),
 'workspace14', (SELECT jsonb_build_object('id', w.id, 'code', w.code,
   'status', w.status, 'row_md5', md5(to_jsonb(w)::text), 'version', w.version,
   'external_key', w.external_key) FROM enterprise_workspaces w WHERE w.id=14),
 'published_count', (SELECT count(*) FROM admin_configurations WHERE status='published'),
 'evidence_policies', (SELECT jsonb_agg(jsonb_build_object('id', id, 'hash', content_hash) ORDER BY id)
   FROM admin_configurations WHERE status='published' AND kind='investment_evidence_policy'),
 'qra_run_count', (SELECT count(*) FROM qra_runs),
 'head', (SELECT version_num FROM alembic_version)
);
ROLLBACK;
"""


def main():
    result = subprocess.run(
        [
            "docker",
            "exec",
            "pypmis-ia-sas-db-1",
            "psql",
            "-U",
            "pypmis",
            "-d",
            "pypmis",
            "-qAt",
            "-c",
            SQL,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    snapshot = json.loads(result.stdout.strip())
    baseline = json.loads(
        (DATA / "operational-before.json").read_text(encoding="utf-8")
    )
    # Preserve the actual current observation even if the assertion detects change.
    (DATA / "operational-after.json").write_text(
        json.dumps(snapshot, indent=2), encoding="utf-8"
    )
    assert snapshot == baseline, (
        "Operational preservation mismatch; inspect actual before/after, do not conceal"
    )
    print(
        "Operational Project14, Workspaces, published policies, QRA count and Alembic head unchanged"
    )


if __name__ == "__main__":
    main()
