"""Bind closeout controls to one named execution and fail closed on missing proof."""

import json
import re
import sys
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree

from chromium_gate import snapshot as browser_sources
from freeze import HEAD, QA, snapshot
from postgres_regression import sources as postgres_sources

PASS_MARKER = "WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION_RELEASE_VALIDATED"
READY_MARKER = "READY_FOR_WAVE_O2C_CONTRACTS_COMMITMENTS_FOUNDATION"
BLOCKED_MARKER = "WAVE_O2B_RELEASE_BLOCKED"


def load(path):
    return json.loads(path.read_text("utf-8-sig")) if path.is_file() else {}


def cases(path, match=None):
    if not path.is_file():
        return []
    return [
        row
        for row in ElementTree.parse(path).iter("testcase")
        if not match or match in f"{row.get('classname')}.{row.get('name')}"
    ]


def passed(rows, minimum=1):
    return len(rows) >= minimum and not any(
        row.find(tag) is not None
        for row in rows
        for tag in ("failure", "error", "skipped")
    )


def failure_summary(rows):
    def sanitized(detail):
        message = re.sub(
            r"eyJ[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2}",
            "[token oculto]",
            detail.get("message") or "",
        )
        return " ".join(message.split())[:185]

    return [
        {
            "case": f"{row.get('classname')}.{row.get('name')}",
            "outcome": tag,
            "message": sanitized(detail),
        }
        for row in rows
        for tag in ("failure", "error", "skipped")
        if (detail := row.find(tag)) is not None
    ]


def verdict(attempt):
    frozen = load(QA / "release" / f"freeze-{attempt}.json")
    current = snapshot()
    verified = bool(frozen and frozen.get("source") == current)
    history = load(QA / "migration/history.json")
    migration_path = QA / "migration/history.xml"
    migration = bool(
        history.get("result") == "PASS"
        and history.get("head") == HEAD
        and history.get("database_name") == "o2b_close_migration"
        and history.get("alembic_revisions") == 78
        and passed(cases(migration_path), 4)
    )
    pg = {
        wave: load(
            QA / "postgres-regression" / wave / attempt / "postgres-source-proof.json"
        )
        for wave in ("o1", "o2a", "o2b")
    }
    browsers = {
        wave: load(QA / "chromium" / wave / attempt / "browser-source-proof.json")
        for wave in ("o2a", "o2b")
    }

    expected_web, expected_pg = browser_sources(), postgres_sources()

    def lane(proof, relative, is_browser):
        directory = QA / relative
        artifacts = proof.get("artifact_sha256", {})
        rows = cases(directory / "junit.xml")
        return (
            proof.get("result") == "PASS"
            and proof.get("git_commit") == current["git_commit"]
            and proof.get("alembic_head") == HEAD
            and proof.get("source_unchanged") is True
            and proof.get("source_sha256")
            == (expected_web if is_browser else expected_pg)
            and "junit.xml" in artifacts
            and passed(rows, 2 if is_browser else 1)
            and all(
                Path(name).name == name
                and (directory / name).is_file()
                and sha256((directory / name).read_bytes()).hexdigest() == digest
                for name, digest in artifacts.items()
            )
        )

    pg_status = {
        wave: lane(proof, f"postgres-regression/{wave}/{attempt}", False)
        for wave, proof in pg.items()
    }
    web_status = {
        wave: lane(proof, f"chromium/{wave}/{attempt}", True)
        for wave, proof in browsers.items()
    }
    consumer = QA / "postgres" / f"consumer-{attempt}" / "junit.xml"
    profile_proof = load(consumer.parent / "profile-proof.json")
    profiles_match = bool(
        consumer.is_file()
        and profile_proof.get("head") == HEAD
        and profile_proof.get("attempt") == attempt
        and profile_proof.get("read_only") == "on"
        and profile_proof.get("junit_sha256")
        == sha256(consumer.read_bytes()).hexdigest()
        and {row["consumer"] for row in profile_proof.get("profiles", [])}
        == {"COST", "PROGRESS", "FORECAST"}
        and all(
            row["status"] == "published"
            and re.fullmatch(r"[0-9a-f]{64}", row["content_hash"])
            for row in profile_proof["profiles"]
        )
    )
    comparison_path = QA / "baseline-gate06d-e5747a6/junit.xml"
    comparison_failures = failure_summary(cases(comparison_path))
    adoption = {
        key: profiles_match
        and passed(cases(consumer, f"test_procurement_{key}_consumer_release"))
        for key in ("cost", "progress", "forecast")
    }
    source_policies = passed(cases(consumer, "test_procurement_consumer_sources"), 4)
    before, after = (
        load(QA / "project-14" / f"preservation-{phase}.json").get("observation", {})
        for phase in ("before", "after")
    )
    preserved = bool(
        before.get("read_only")
        and after.get("read_only")
        and all(
            key in before and before[key] == after.get(key)
            for key in (
                "database",
                "canonical_id14_row_sha256",
                "legacy_project14",
                "project14_row_sha256",
                "project14_references",
            )
        )
    )
    performance = load(QA / "performance" / f"{attempt}.json")
    measured = len(performance.get("operations", [])) == 6 and all(
        len(row["samples_ms"]) == 3 and row["response_bytes"] > 0
        for row in performance["operations"]
    )
    # These are distinct from the exercised adoption happy paths and resolver checks.
    # The final-a evidence does not certify these mandatory cases.
    follow_up = {
        "CLOSE-PROG-LINEAGE": (
            "Rechazar evidencia reemplazada en Progress (sección 20)",
            "Progress conserva la evidencia física histórica",
            "Reemplazo de referencia gobernada",
            f"consumer-progress/{attempt}/junit.xml",
            "La adopción HTTP pasó, pero no se probó una fuente reemplazada en Progress.",
            "Probar que un vínculo reemplazado no se readopta, sin invalidar hechos físicos históricos.",
        ),
        "CLOSE-FCST-SOURCES": (
            "Señales y referencias obsoletas de Forecast (secciones 22 y 24)",
            "Resolver de señales y bitácora de Forecast",
            "Cambio, sucesión e inactivación por HTTP",
            f"consumer-forecast/{attempt}/junit.xml",
            "No hay fechas pronosticadas de adjudicación y orden separadas de las planificadas. Falta demostrar rechazo HTTP ante cambio, sucesión de PO e inactivación.",
            "Identificar las dos fuentes de fecha pronosticada sin sustituirlas por fechas planificadas. Probar cambio, revisión sucesora e inactivación por HTTP.",
        ),
        "CLOSE-AUTH-WRITE": (
            "Intento directo de escritura desde Procurement (sección 29)",
            "Permisos propios y contratos sin escritura cruzada",
            "Rechazo por cada autoridad consumidora",
            f"postgres/consumer-{attempt}/junit.xml",
            "Las huellas confirman que no hubo escrituras indirectas, pero no se probó el intento directo contra cada autoridad.",
            "Con un actor exclusivo de Procurement, probar el rechazo de comandos nativos de Cost, Progress y Forecast y comparar huellas.",
        ),
    }
    controls = [
        (
            "CLOSE-FREEZE",
            "Fuente congelada",
            "freeze.py",
            "Comparar huellas",
            f"release/freeze-{attempt}.json",
            verified,
            "La fuente local incluye cambios sin commit.",
        ),
        (
            "CLOSE-MIG",
            "Migración histórica desde base física vacía",
            "DDL pre-Alembic y revisiones 0001 a 0078",
            "test_procurement_o2b_close_history_migration",
            "migration/history.xml",
            migration,
            "Verificar catálogo, integridad e ida y vuelta hasta 0075.",
        ),
        *[
            (
                f"CLOSE-PG-{wave.upper()}",
                f"Regresión funcional {wave.upper()}",
                "postgres_regression.py",
                "Suite PostgreSQL existente",
                f"postgres-regression/{wave}/{attempt}/junit.xml",
                status,
                "Ejecutar la suite completa sobre la fuente congelada.",
            )
            for wave, status in pg_status.items()
        ],
        *[
            (
                f"CLOSE-WEB-{wave.upper()}",
                f"Chromium crítico {wave.upper()}",
                "chromium_gate.py",
                "Contexto y ciclo real",
                f"chromium/{wave}/{attempt}/junit.xml",
                status,
                "Verificar estado AWP y contexto canónico en navegador real.",
            )
            for wave, status in web_status.items()
        ],
        *[
            (
                f"CLOSE-{domain.upper()}",
                f"Adopción explícita desde {domain.title()}",
                "procurement_consumers/router.py",
                f"test_procurement_{domain}_consumer_release",
                f"consumer-{domain}/{attempt}/junit.xml",
                status,
                "Validar decisión y comparar las autoridades antes y después.",
            )
            for domain, status in adoption.items()
        ],
        (
            "CLOSE-NEG",
            "Versiones, hashes y fuentes rechazadas",
            "procurement_foundation/consumer_sources.py",
            "test_procurement_consumer_sources",
            f"regression/integration-policies/{attempt}/junit.xml",
            source_policies,
            "Ejecutar los casos negativos del contrato de origen.",
        ),
        *[
            (key, requirement, implementation, test, evidence, False, action)
            for key, (
                requirement,
                implementation,
                test,
                evidence,
                _,
                action,
            ) in follow_up.items()
        ],
        (
            "CLOSE-P14",
            "Proyecto 14 preservado",
            "preservation.py",
            "Comparación de solo lectura",
            "project-14/preservation-{before,after}.json",
            preserved,
            "Comparar identidad canónica, fila legacy y referencias.",
        ),
        (
            "CLOSE-PERF",
            "Rendimiento de seis lecturas locales",
            "test_procurement_consumer_release.py",
            "Tres muestras por operación",
            f"performance/{attempt}.json",
            measured,
            "Registrar mediana y tamaño sin inferir SLA.",
        ),
    ]
    g01 = (
        verified and migration and all(pg_status.values()) and all(web_status.values())
    )
    g02 = (
        verified
        and all(adoption.values())
        and source_policies
        and passed(cases(consumer), 7)
        and all(row[5] for row in controls if row[0] in follow_up)
    )
    release = g01 and g02 and preserved and measured
    blockers = []
    for name, _, _, _, path, status, action in controls:
        if status:
            continue
        rows = cases(QA / path) if path.endswith("junit.xml") else []
        failures = failure_summary(rows)
        if failures and name == "CLOSE-PG-O1":
            action = (
                "Conciliar los contratos de navegación de Gate06D con los nombres y rutas "
                "operacionales vigentes; corregir el origen de los fallos y repetir O1 sin excluir pruebas."
            )
        blockers.append(
            {
                "control": name,
                "evidence": path,
                "severity": "S2",
                "action": action,
                "failures": failures,
                "state": "FAIL" if failures else "EVIDENCE_INCOMPLETE",
                "finding": follow_up[name][4] if name in follow_up else "",
                "baseline_reproduced": sorted(
                    {row["case"] for row in failures}
                    & {row["case"] for row in comparison_failures}
                )
                if name == "CLOSE-PG-O1"
                else [],
            }
        )
    return {
        "attempt": attempt,
        "freeze": frozen,
        "migration": history,
        "pg": pg,
        "browsers": browsers,
        "g01": "CLOSED" if g01 else "OPEN",
        "g02": "CLOSED" if g02 else "OPEN",
        "controls": controls,
        "adoption": adoption,
        "preservation": after if preserved else {},
        "performance": performance if measured else {},
        "baseline_comparison": "baseline-gate06d-e5747a6/baseline-proof.json"
        if comparison_failures
        else "",
        "consumer_profiles": profile_proof.get("profiles", [])
        if profiles_match
        else [],
        "decision": PASS_MARKER if release else BLOCKED_MARKER,
        "readiness": READY_MARKER if release else "",
        "blockers": blockers,
    }


if __name__ == "__main__":
    attempt = sys.argv[1]
    result = verdict(attempt)
    report = {k: result[k] for k in ("decision", "readiness", "g01", "g02", "blockers")}
    if len(sys.argv) == 3 and sys.argv[2] == "--record":
        report["checks"] = {
            row[0]: {"evidence": row[4], "verified": row[5]}
            for row in result["controls"]
        }
        (QA / "release" / f"decision-{attempt}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
        )
    print(json.dumps(report, ensure_ascii=True, indent=2))
