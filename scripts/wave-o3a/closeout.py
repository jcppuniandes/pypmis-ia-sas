"""Require the actual O3A evidence before recording its isolated release decision."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from report_content import OUT, QA, read

MARKER = "WAVE_O3A_CONSTRUCTION_FIELD_OPERATIONS_FOUNDATION_RELEASE_VALIDATED"


def junit(relative):
    suites = list(ET.parse(QA / relative).getroot().iter("testsuite"))
    assert suites
    for suite in suites:
        assert int(suite.get("tests", 0)) > 0
        assert not any(
            int(suite.get(key, 0)) for key in ("failures", "errors", "skipped")
        ), relative


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-reviewed", action="store_true")
    args = parser.parse_args()
    evidence = [
        "core-policy-junit.xml",
        "core-release-junit.xml",
        "execution-policy-final-junit.xml",
        "consumer-policy-junit.xml",
        "consumer-junit.xml",
        "authority-negatives-junit.xml",
        "regression-junit.xml",
        "chromium-final-junit.xml",
        "frontend-final/junit.xml",
    ]
    for name in evidence:
        junit(name)
    assert read("migration/proof.json")["result"] == "PASS"
    assert read("migration/proof.json")["record_guard_count"] == 17
    before, after = (
        read("project-14/preservation-before.json"),
        read("project-14/preservation-after.json"),
    )
    assert (
        before["read_only"]
        and after["read_only"]
        and before["observation"] == after["observation"]
    )
    (QA / "project-14/compare.json").write_text(
        json.dumps(
            {
                "result": "PASS",
                "read_only": True,
                "observations_equal": True,
                "legacy_reference_checks": len(
                    before["observation"]["project14_references"]
                ),
                "workspace_reference_checks": len(
                    before["observation"]["canonical_workspace14_references"]
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert (
        read("browser-summary.json")["passed"]
        and not read("browser-summary.json")["errors"]
    )
    assert (
        read("frontend-final/proof.json")["passed"]
        and read("frontend-final/proof.json")["source_unchanged"]
    )
    reads = read("consumer-performance.json")["reads"]
    assert len(reads) == 9 and all(
        len(row["samples_ms"]) == len(row["bytes"]) == 3 for row in reads
    )
    contracts = read("contracts-performance.json")
    assert (
        contracts["result"] == "PASS"
        and contracts["before_hashes"] == contracts["after_hashes"]
    )
    assert not contracts["read_mutations"] and all(
        len(row["samples"]) == 3 for row in contracts["metrics"].values()
    )
    defects = [
        [
            "O3A-S2-01",
            "S2",
            "Observación rechazada y terminales SQL",
            "CERRADO",
            "Solo VERIFIED adoptable y guardas terminales correctas",
        ],
        [
            "O3A-S2-02",
            "S2",
            "Adopción AWP repetida tras rechazo",
            "CERRADO",
            "Se comprueba cualquier ADOPT anterior del linaje",
        ],
        [
            "O3A-S2-03",
            "S2",
            "Fuentes de acumulados y ramas de mediciones pendientes",
            "CERRADO",
            "Pins acumulados y bloqueo de borrador pendiente",
        ],
        [
            "O3A-S2-04",
            "S2",
            "Vigencia IFC en la fecha de ejecución",
            "CERRADO",
            "Reglas temporales nativas de Engineering",
        ],
        [
            "O3A-S2-05",
            "S2",
            "CWA incompatible entre referencias",
            "CERRADO",
            "Validación explícita e inferida sin crear jerarquía paralela",
        ],
        [
            "O3A-S2-06",
            "S2",
            "Selección web de identidades canónicas",
            "CERRADO",
            "Normalizer target_id y prueba Chromium real",
        ],
        [
            "O3A-S2-07",
            "S2",
            "Tipo de evidencia rechazado por Progress",
            "CERRADO",
            "Reutilización de FIELD_REPORT y fuente tipada congelada",
        ],
        [
            "O3A-S3-UI01",
            "S3",
            "Indicadores del padre nativo requieren refresco manual",
            "ABIERTO",
            "Usar Actualizar en Progress AWP o Cost después de adoptar",
        ],
        [
            "O3A-S3-01",
            "S3",
            "Recuperación de reservas y conciliación de correcciones adoptadas",
            "ABIERTO",
            "Mantener cierre seguro y tratamiento gobernado del receptor",
        ],
    ]
    assert not [
        row for row in defects if row[1] in {"S1", "S2"} and row[3] == "ABIERTO"
    ]
    decision = {
        "status": "VALIDADO EN ENTORNO AISLADO",
        "functional_pass": True,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "evidence": evidence,
        "criteria": {
            key: "PASS"
            for key in (
                "PostgreSQL",
                "Consumers",
                "Chromium",
                "Preservation",
                "Regression",
                "Performance",
                "Defects",
            )
        },
        "defects": defects,
        "notes": [
            "Las pruebas obligatorias aprobaron. No hay defectos S1 o S2 conocidos abiertos en el corte.",
            "La validación se realizó exclusivamente en bases aisladas. El proyecto 14 conservó sus hashes y referencias.",
            "Las deudas O2C-S3-01 y O2C-S3-02 se mantienen. Las mejoras de las guardas O3A no se declaran cierre de O2C.",
            "Progress conserva su aprobación independiente. Field no genera Actual Cost, efectos contractuales ni fechas P6.",
            "La liberación técnica no equivale a aceptación formal de negocio ni a despliegue en producción.",
        ],
        "artifacts_reviewed": args.artifacts_reviewed,
        "production_changed": False,
        "project14_written": False,
    }
    if args.artifacts_reviewed:
        render = read("word-pages-final-1/render-provenance.json")
        assert len(render["pages"]) == 11
        assert len(list((QA / "matrix-render").glob("*.png"))) == 19
        targets = [
            OUT / ("P&Pmis_Wave_O3A_Construction_Field_Operations_" + name)
            for name in ("Technical_Report.docx", "Traceability.xlsx")
        ]
        assert all(path.is_file() and path.stat().st_size > 1000 for path in targets)
        decision["artifacts"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in targets
        }
        decision["release_marker"] = MARKER
    (QA / "release-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        MARKER
        if args.artifacts_reviewed
        else "Functional evidence PASS; artifact review gate remains"
    )


if __name__ == "__main__":
    main()
