"""Read only evidence tied to the selected CLOSE-2 source freeze."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from validate import HEAD, QA, chromium, postgres, snapshot

VALIDATED = "WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION_RELEASE_VALIDATED"
READY = "READY_FOR_WAVE_O2C_CONTRACTS_COMMITMENTS_FOUNDATION"
BLOCKED = "WAVE_O2B_RELEASE_BLOCKED"


def read(path):
    return json.loads(path.read_text("utf-8-sig")) if path.is_file() else {}


def junit(path):
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if path.is_file():
        for case in ElementTree.parse(path).iter("testcase"):
            outcome = next(
                (
                    key
                    for key, tag in (
                        ("failed", "failure"),
                        ("errors", "error"),
                        ("skipped", "skipped"),
                    )
                    if case.find(tag) is not None
                ),
                "passed",
            )
            counts[outcome] += 1
    return counts


def integrity(directory, hashes, required):
    return all(name in hashes for name in required) and all(
        Path(name).name == name
        and (directory / name).is_file()
        and chromium.digest(directory / name) == value
        for name, value in hashes.items()
    )


def started_after_freeze(directory, xml, started, frozen_at):
    if not frozen_at or not (directory / xml).is_file():
        return False
    if not started:
        suites = ElementTree.parse(directory / xml).iter("testsuite")
        stamps = [node.get("timestamp") for node in suites if node.get("timestamp")]
        if not stamps:
            return False
        started = stamps[0]
    start, freeze_time = (
        datetime.fromisoformat(value) for value in (started, frozen_at)
    )
    return (
        start.tzinfo is not None
        and freeze_time.tzinfo is not None
        and start >= freeze_time
    )


def build(attempt, o2a_retry=None):
    freeze_path = QA / "release" / f"freeze-{attempt}.json"
    frozen = read(freeze_path)
    current = snapshot()
    still_frozen = bool(frozen and current == frozen["source"])
    freeze_sha = chromium.digest(freeze_path) if frozen else ""
    expected_chromium = chromium.snapshot()
    expected_postgres = postgres.sources()
    o2a_browser_attempt = attempt
    if o2a_retry:
        if not re.fullmatch(re.escape(attempt) + r"-retry[1-9][0-9]*", o2a_retry):
            raise ValueError("Invalid O2A retry identity")
        retry_freeze = QA / "release" / f"freeze-{o2a_retry}.json"
        if (
            not frozen
            or not retry_freeze.is_file()
            or chromium.digest(retry_freeze) != freeze_sha
        ):
            raise RuntimeError(
                "O2A retry does not share the identical frozen source manifest"
            )
        original = read(QA / "chromium/o2a" / attempt / "browser-source-proof.json")
        if original.get("result") != "FAIL":
            raise RuntimeError("A retry may only replace a failed original lane")
        o2a_browser_attempt = o2a_retry

    def lane(relative, manifest, files, xml="junit.xml", expected_count=None):
        directory = QA / relative
        proof = read(directory / manifest)
        tests = junit(directory / xml)
        hashes = proof.get("evidence_sha256") or proof.get("artifact_sha256", {})
        started = proof.get("started_at_utc", "")
        source = proof.get("source_sha256", {})
        if manifest == "consumer-proof.json":
            source_ok = (
                proof.get("freeze_sha256") == freeze_sha
                and proof.get("source_unchanged") is True
            )
        elif manifest == "postgres-source-proof.json":
            source_ok = (
                source == expected_postgres and proof.get("source_unchanged") is True
            )
        elif manifest == "browser-source-proof.json":
            source_ok = (
                source == expected_chromium and proof.get("source_unchanged") is True
            )
        else:
            source_ok = source == current["sha256"]
        ok = bool(
            still_frozen
            and proof.get("result") == "PASS"
            and source_ok
            and started_after_freeze(directory, xml, started, frozen["frozen_at_utc"])
            and proof.get("git_commit") == current["git_commit"]
            and proof.get("alembic_head") == HEAD
            and tests["passed"]
            and not any(tests[key] for key in ("failed", "errors", "skipped"))
            and (expected_count is None or tests["passed"] == expected_count)
            and integrity(directory, hashes, [xml, *files])
        )
        return {
            "pass": ok,
            "tests": tests,
            "evidence": f"{relative}/{xml}",
            "proof": f"{relative}/{manifest}",
            "published_profile": proof.get("published_profile"),
        }

    pg_o1 = lane(
        f"pg-o1/o1/{attempt}", "postgres-source-proof.json", [], expected_count=1052
    )
    progress = lane(
        f"progress-lineage/{attempt}",
        "consumer-proof.json",
        ["progress-lineage.json"],
        expected_count=1,
    )
    forecast = lane(
        f"forecast-sources/{attempt}",
        "consumer-proof.json",
        ["milestone-forecast-evidence.json", "expediting-forecast-evidence.json"],
        expected_count=2,
    )
    auth = lane(
        f"auth-write/{attempt}",
        "consumer-proof.json",
        ["authority-proof.json"],
        expected_count=1,
    )
    progress_proof = read(QA / "progress-lineage" / attempt / "progress-lineage.json")
    progress["pass"] = bool(
        progress["pass"]
        and progress_proof.get("result") == "PASS"
        and progress_proof.get("historical_decision_unchanged") is True
        and progress_proof.get("protected_before")
        and progress_proof["protected_before"] == progress_proof.get("protected_after")
        and progress_proof.get("rejected")
        == {
            "old_version": 409,
            "invalid_hash": 409,
            "inactive_iwp": 409,
            "superseded_lineage": 409,
            "wrong_workspace": 403,
            "wrong_tenant": 404,
        }
        and progress_proof.get("lineage_versions")
        == sorted(set(progress_proof.get("lineage_versions", [])))
        and len(progress_proof.get("lineage_versions", [])) == 3
    )
    for name, field in (
        ("milestone", "procurement_vendor_milestones.forecast_date"),
        ("expediting", "procurement_expediting_events.forecast_date"),
    ):
        signal = read(
            QA / "forecast-sources" / attempt / f"{name}-forecast-evidence.json"
        )
        first, current_pin = (signal.get(key, {}) for key in ("initial", "successor"))
        dates = {
            signal.get("planned_reference"),
            first.get("source_forecast_date"),
            current_pin.get("source_forecast_date"),
        }
        ids = {
            first.get("source_entity_id"),
            current_pin.get("source_entity_id"),
            signal.get("inactive_source_id"),
        }
        forecast["pass"] = bool(
            forecast["pass"]
            and signal.get("source_field") == field
            and len(dates) == len(ids) == 3
            and None not in dates
            and None not in ids
            and first.get("source_hash")
            and first["source_hash"] != current_pin.get("source_hash")
            and signal.get("approved_forecast_http_unchanged") is True
            and signal.get("draft_forecast_http_unchanged") is True
            and signal.get("authority_sql_before")
            and signal["authority_sql_before"] == signal.get("authority_sql_after")
        )
    auth_proof = read(QA / "auth-write" / attempt / "authority-proof.json")
    denials = auth_proof.get("denials", [])
    auth["pass"] = bool(
        auth["pass"]
        and auth_proof.get("result") == "PASS"
        and auth_proof.get("role") == "procurement_buyer"
        and auth_proof.get("positive_procurement") == {"read": 200, "write": 201}
        and len(denials) == 10
        and {row["status"] for row in denials} == {403}
        and {
            domain: sum(row["domain"] == domain for row in denials)
            for domain in (
                "cost",
                "progress",
                "operational",
                "forecast",
            )
        }
        == {"cost": 4, "progress": 2, "operational": 1, "forecast": 3}
        and auth_proof.get("before_sha256")
        and auth_proof["before_sha256"] == auth_proof.get("after_sha256")
        and len(auth_proof.get("before_tables", {})) == 20
        and auth_proof["before_tables"] == auth_proof.get("after_tables")
    )
    regressions = {
        "O1 PostgreSQL": pg_o1,
        "O2A PostgreSQL": lane(
            f"postgres/o2a/{attempt}",
            "postgres-source-proof.json",
            [],
            expected_count=59,
        ),
        "O2B PostgreSQL": lane(
            f"postgres/o2b/{attempt}",
            "postgres-source-proof.json",
            [],
            expected_count=11,
        ),
        "Consumidores y políticas": lane(
            f"postgres/{attempt}", "consumer-proof.json", [], expected_count=7
        ),
        "Chromium O2A": lane(
            f"chromium/o2a/{o2a_browser_attempt}",
            "browser-source-proof.json",
            ["browser-uat.json", "project-context.json"],
            expected_count=2,
        ),
        "Chromium O2B": lane(
            f"chromium/o2b/{attempt}",
            "browser-source-proof.json",
            ["browser-uat.json", "project-context.json"],
            expected_count=2,
        ),
        "Chromium consumidores": lane(
            f"chromium/o2b/{attempt}",
            "consumer-browser-source-proof.json",
            ["consumer-browser-proof.json"],
            xml="consumer-junit.xml",
            expected_count=1,
        ),
    }
    before, after = (
        read(QA / "project-14" / f"preservation-{phase}.json").get("observation", {})
        for phase in ("before", "after")
    )
    protected = bool(
        before.get("read_only") is True
        and after.get("read_only") is True
        and before["canonical_project14"]["id"] == 14
        and all(
            before[key] == after[key]
            for key in (
                "database",
                "canonical_id14_row_sha256",
                "legacy_project14",
                "project14_row_sha256",
                "project14_references",
            )
        )
    )
    profile_path = QA / "release" / f"profiles-{attempt}.json"
    profiles = read(profile_path)
    profile_lanes = profiles.get("lanes", [])
    profiles_ok = bool(
        profiles.get("result") == "PASS"
        and profiles.get("read_only") is True
        and profiles.get("database") == "o2b_close_consumers"
        and profiles.get("git_commit") == current["git_commit"]
        and profiles.get("alembic_head") == HEAD
        and profiles.get("attempt") == attempt
        and profiles.get("freeze_sha256") == freeze_sha
        and {item["lane"]: len(item["adoptions"]) for item in profile_lanes}
        == {"progress-lineage": 2, "forecast-sources": 4, "postgres": 8}
        and all(
            item["proof"] == f"{item['lane']}/{attempt}/consumer-proof.json"
            and item["junit"] == f"{item['lane']}/{attempt}/junit.xml"
            and integrity(
                QA / item["lane"] / attempt,
                {
                    "junit.xml": item["junit_sha256"],
                    "consumer-proof.json": item["proof_sha256"],
                },
                ["junit.xml", "consumer-proof.json"],
            )
            for item in profile_lanes
        )
    )
    details = [
        (
            "CLOSE-PG-O1",
            pg_o1,
            "Contratos de navegación Gate06D desfasados respecto al catálogo canónico.",
            "Repetir la suite completa O1 sin exclusiones tras conciliar rutas y permisos.",
        ),
        (
            "CLOSE-PROG-LINEAGE",
            progress,
            "El filtro de Progress no reconocía el estado nativo SUPERSEDED de un IWP.",
            "Validar adopción del sucesor, rechazo de la referencia anterior y preservación SQL.",
        ),
        (
            "CLOSE-FCST-SOURCES",
            forecast,
            "Faltaba evidencia HTTP de sucesión e inactivación de señales reales.",
            "Ejecutar los dos casos nativos con versiones, huellas y Forecast aprobado intacto.",
        ),
        (
            "CLOSE-AUTH-WRITE",
            auth,
            "Faltaba intentar escrituras nativas con el rol exclusivo de Procurement.",
            "Verificar rechazo de los comandos nativos y coincidencia de las huellas SQL.",
        ),
    ]
    controls = [
        {
            "id": name,
            "status": "CLOSED" if lane_info["pass"] else "OPEN",
            "evidence": lane_info["evidence"],
            "severity": None if lane_info["pass"] else "S2",
            "observation": {
                "CLOSE-PG-O1": "Catálogo Gate06D conciliado. O1: 1.052 aprobadas, sin fallos ni omisiones.",
                "CLOSE-PROG-LINEAGE": "Se rechazó el vínculo sustituido; despacho y decisión anterior conservaron su huella.",
                "CLOSE-FCST-SOURCES": "Dos fuentes nativas aprobaron sucesión e inactivación. El Forecast aprobado quedó intacto.",
                "CLOSE-AUTH-WRITE": "10 comandos rechazados con 403; las huellas SQL de 20 tablas no cambiaron.",
            }[name]
            if lane_info["pass"]
            else root_cause,
            "action": action if not lane_info["pass"] else "",
            "tests": lane_info["tests"],
        }
        for name, lane_info, root_cause, action in details
    ]
    g01 = pg_o1["pass"] and all(
        regressions[key]["pass"]
        for key in ("O2A PostgreSQL", "O2B PostgreSQL", "Chromium O2A", "Chromium O2B")
    )
    g02 = (
        progress["pass"]
        and forecast["pass"]
        and auth["pass"]
        and regressions["Consumidores y políticas"]["pass"]
        and regressions["Chromium consumidores"]["pass"]
        and profiles_ok
    )
    residual = [row for row in controls if row["status"] == "OPEN"]
    for name, row in regressions.items():
        if not row["pass"] and name != "O1 PostgreSQL":
            residual.append(
                {
                    "id": name,
                    "severity": "S2",
                    "evidence": row["evidence"],
                    "observation": "No hay una prueba aprobada y vinculada a este freeze.",
                    "action": "Completar o corregir el carril aislado y conservar su JUnit.",
                }
            )
    if not protected:
        residual.append(
            {
                "id": "PROJECT-14",
                "severity": "S2",
                "evidence": "project-14/",
                "observation": "Comparación canónica de solo lectura no acreditada.",
                "action": "Capturar y comparar las dos observaciones sin escribir datos.",
            }
        )
    if not profiles_ok:
        residual.append(
            {
                "id": "PROFILE-PROVENANCE",
                "severity": "S2",
                "evidence": f"release/profiles-{attempt}.json",
                "observation": "No se acreditaron las revisiones y huellas de los perfiles publicados.",
                "action": "Verificar el vínculo SQL con las adopciones y sus JUnit del mismo corte.",
            }
        )
    approved = bool(still_frozen and g01 and g02 and protected and not residual)
    matrix_regressions = []
    for identifier, name in (
        ("CLOSE-PG-O2A", "O2A PostgreSQL"),
        ("CLOSE-PG-O2B", "O2B PostgreSQL"),
        ("CLOSE-WEB-O2A", "Chromium O2A"),
        ("CLOSE-WEB-O2B", "Chromium O2B"),
        ("CLOSE-COST", "Consumidores y políticas"),
        ("CLOSE-PROGRESS", "Consumidores y políticas"),
        ("CLOSE-FORECAST", "Consumidores y políticas"),
        ("CLOSE-NEG", "Consumidores y políticas"),
    ):
        reg = regressions[name]
        matrix_regressions.append(
            {
                "id": identifier,
                "status": "CLOSED" if reg["pass"] else "OPEN",
                "evidence": reg["evidence"],
                "observation": f"{name}: {reg['tests']['passed']} aprobadas en este corte."
                if reg["pass"]
                else "Falta acreditar en este corte.",
            }
        )
    matrix_regressions.extend(
        [
            {
                "id": "CLOSE-P14",
                "status": "CLOSED" if protected else "OPEN",
                "evidence": "project-14/preservation-{before,after}.json",
                "observation": "Huella canónica y referencias legadas comparadas en solo lectura."
                if protected
                else "Pendiente la comparación final de solo lectura.",
            },
            {
                "id": "CLOSE-FREEZE",
                "status": "CLOSED" if still_frozen else "OPEN",
                "evidence": f"release/freeze-{attempt}.json",
                "observation": "Fuente y pruebas del corte CLOSE-2.",
            },
        ]
    )
    return {
        "attempt": attempt,
        "o2a_browser_attempt": o2a_browser_attempt,
        "profile_provenance": {
            "verified": profiles_ok,
            "evidence": f"release/profiles-{attempt}.json",
            "decisions": sum(len(item["adoptions"]) for item in profile_lanes)
            if profiles_ok
            else 0,
        },
        "decision": VALIDATED if approved else BLOCKED,
        "readiness": READY if approved else "",
        "g01": "CLOSED" if g01 else "OPEN",
        "g02": "CLOSED" if g02 else "OPEN",
        "controls": controls,
        "matrix_regressions": matrix_regressions,
        "regressions": regressions,
        "blockers": residual,
        "freeze": {
            "git_commit": current["git_commit"],
            "alembic_head": HEAD,
            "files": len(current["sha256"]),
            "timestamp": frozen.get("frozen_at_utc"),
            "sha256": freeze_sha,
            "verified": still_frozen,
        },
        "project14": {
            "preserved": protected,
            "references": len(after.get("project14_references", [])),
            "legacy_absent": after.get("legacy_project14") is None,
            "canonical_sha256": after.get("canonical_id14_row_sha256"),
        },
        "auth_write_count": len(denials) if auth["pass"] else 0,
        "open_severity": {"S1": 0, "S2": len(residual), "S3": 0, "S4": 0},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt")
    parser.add_argument("--o2a-retry")
    args = parser.parse_args()
    result = build(args.attempt, args.o2a_retry)
    target = QA / "release" / f"decision-{args.attempt}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(result["decision"])
    print(target)


if __name__ == "__main__":
    main()
