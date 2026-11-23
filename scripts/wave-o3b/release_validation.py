"""Assemble O3B release evidence only after mandatory observed gates succeed."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime

import psycopg
from report_content import MARKER, OUT, QA, ROOT, tests


def read(name):
    return json.loads((QA / name).read_text("utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("technical", "final"))
    args = parser.parse_args()
    suites = [
        "backend-pg-release-20261122/junit.xml",
        "backend-policy-final-20261122/junit.xml",
        "regression/o3a-consumer-junit.xml",
        "frontend-final-v2/unit-junit.xml",
    ]
    (QA / "verified-suites.json").write_text(
        json.dumps({"suites": [{"path": path} for path in suites]}, indent=2),
        encoding="utf-8",
    )
    results = tests()
    assert len(results) == 4 and all(
        row[-1] == "PASS" and row[-2] == 0 for row in results
    )
    for path in (
        "backend-pg-release-20261122/result.json",
        "backend-policy-final-20261122/result.json",
        "frontend-final-v2/result.json",
        "backend-lint.json",
    ):
        assert read(path)["status"] == "PASS", path
    for directory in ("backend-pg-release-20261122", "backend-policy-final-20261122"):
        for name, expected in read(directory + "/result.json")["source_sha256"].items():
            assert digest(ROOT / name) == expected, name
    for name, expected in read("frontend-final-v2/result.json")[
        "source_sha256"
    ].items():
        assert digest(ROOT / "frontend" / name) == expected, name
    migration = read("migration/round-trip.json")
    assert (
        migration["status"] == "PASS"
        and migration["scoped_guarded_tables"] == 17
        and migration["guard_triggers"] == 19
    )
    assert read("migration/populated-refusal.json")["status"] == "PASS"
    assert read("microclose/complete.json")["original_artifacts_preserved"]
    browser = read("browser-summary.json")
    assert (
        browser["passed"]
        and browser["status"] == "PASS_SEGMENTED"
        and len(browser["steps"]) == 62
        and not browser["errors"]
    )
    for row in browser["segments"] + browser["screenshots"]:
        assert digest(QA / row["path"]) == row["sha256"], row["path"]
    assert (
        read("consumer-evidence.json")["status"] == "PASS"
        and read("consumer-evidence.json")["native_progress_approved"]
    )
    remediation = read("execution/real-remediation.json")
    assert remediation["historical_fail_preserved"]
    assert (
        remediation["unchanged_native_signatures_before"]
        == remediation["unchanged_native_signatures_after"]
    )
    before = read("project-14/preservation-before.json")
    after = read("project-14/preservation-after.json")
    assert (
        before["observation"] == after["observation"]
        and before["read_only"]
        and after["read_only"]
    )
    performance = read("consumer-performance.json")
    assert performance["no_sql_writes"] and len(performance["reads"]) == 10
    assert all(
        len(row["samples_ms"]) == len(row["bytes"]) == len(row["rows"]) == 3
        for row in performance["reads"]
    )
    legacy = read("regression/legacy-regression-proof.json")
    assert (
        legacy["status"] == "PASS"
        and legacy["contracts_get_business_dml"] == 0
        and legacy["contracts_observed_hashes_unchanged"]
    )
    assert (
        legacy["historical_o3a_before_hashes"] == legacy["historical_o3a_after_hashes"]
    )
    original_app = subprocess.check_output(
        ["git", "show", "HEAD:frontend/src/App.tsx"], cwd=ROOT
    )
    actual_app = (ROOT / "frontend/src/App.tsx").read_bytes().replace(b"\r\n", b"\n")
    assert original_app.replace(b"\r\n", b"\n") == actual_app
    with psycopg.connect(
        "host=127.0.0.1 port=5432 dbname=pypmis user=pypmis password=pypmis"
    ) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        normal_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall()
        quality_tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'quality_%'"
        ).fetchall()
        assert not quality_tables, "Ordinary DB must not receive O3B tables"
        connection.rollback()
    (QA / "normal-database-read-only.json").write_text(
        json.dumps(
            {
                "observed_at": datetime.now(UTC).isoformat(),
                "read_only": True,
                "quality_tables": quality_tables,
                "alembic_revision": normal_revision,
                "App_tsx_unchanged": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    defects = [
        [
            "O3B-S2-01",
            "S2",
            "Cobertura Quantity con avance acumulado histórico",
            "CLOSED",
            "Ledger Field por pin y aprobación nativa PostgreSQL",
        ],
        [
            "O3B-S2-02",
            "S2",
            "Aceptación superior a cantidad explícitamente inspeccionada",
            "CLOSED",
            "Cap por control y negativos unitarios y PostgreSQL",
        ],
        [
            "O3B-S2-03",
            "S2",
            "Autoinvalidación AWP y DTO mínimo de referencia",
            "CLOSED",
            "Proyección técnica y regresión PostgreSQL y unitaria",
        ],
        [
            "O3B-S2-04",
            "S2",
            "Lectura actual no revalidaba todos los requisitos del resultado",
            "CLOSED",
            "Delegación al validador IFC checklist y equipos",
        ],
        [
            "O3B-S2-05",
            "S2",
            "Pendientes HOLD WITNESS y aceptación ausentes de Look-Ahead",
            "CLOSED",
            "Consulta derivada pura con filtros y ciclo PostgreSQL",
        ],
        [
            "O3B-S3-UI01",
            "S3",
            "Carreras y conteo base incorrecto del arnés Chromium",
            "CLOSED",
            "Arnés corregido y tres segmentos vinculados sin recrear hechos",
        ],
    ]
    document_reviewed = False
    if args.stage == "final":
        word, matrix = read("word-qa.json"), read("matrix-qa.json")
        assert word["status"] == matrix["status"] == "PASS"
        assert (
            word["all_pages_reviewed"]
            and matrix["all_sheets_reviewed"]
            and matrix["sheets"] == 20
        )
        assert digest(OUT / word["filename"]) == word["sha256"]
        assert digest(OUT / matrix["filename"]) == matrix["sha256"]
        document_reviewed = True
    proof = {
        "status": MARKER if document_reviewed else "VALIDADO EN ENTORNO AISLADO",
        "technical_status": "PASS",
        "artifact_review_completed": document_reviewed,
        "checked_at": datetime.now(UTC).isoformat(),
        "ordinary_database_used_for_writes": False,
        "project14_preserved": True,
        "App_tsx_unchanged": True,
        "production_deployed": False,
        "next_wave_started": False,
        "open_S1": 0,
        "open_S2": 0,
        "defects": defects,
        "browser_method": "PASS_SEGMENTED same persisted chain; final PG independently verifies later hardening",
        "suites": results,
        "inherited_debt_retained": [
            "O2C-S3-01",
            "O2C-S3-02",
            "O3A-S3-UI01",
            "O3A-S3-01",
        ],
        "fail_closed_provider_limits": [
            "NCR-bound Engineering USE_AS_IS decision",
            "Procurement material corrective-action provider",
        ],
    }
    (QA / "release-decision.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: proof[key]
                for key in (
                    "status",
                    "technical_status",
                    "artifact_review_completed",
                    "open_S1",
                    "open_S2",
                )
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
