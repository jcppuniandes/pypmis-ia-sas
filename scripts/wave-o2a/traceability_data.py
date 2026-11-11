"""Map prompt requirements, actual tests, API and known limits to Excel rows."""

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2a-20261109"
DEFAULT_SPEC = (
    ROOT.parent.parent
    / "P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O2A_ENGINEERING_FOUNDATION.md"
)
TEST = {
    "register": "test_deliverable_identity_catalog_pagination_etag_and_idempotency",
    "cde": "test_cde_link_for_construction_and_upload_are_not_approval_or_release",
    "reviews": "test_review_comments_response_revise_resubmit_check_and_approval",
    "reject": "test_rejection_is_explicit_and_requires_successor",
    "ifc": "test_ifc_release_is_independent_immutable_and_successor_is_effective_by_cutoff",
    "mappings": "test_mapping_is_many_to_many_typed_append_only_and_project_scoped",
    "schedule": "test_schedule_successor_stales_mapping_without_remapping",
    "awp": "test_awp_assesses_ifc_evidence_without_auto_clear_or_package_release",
    "readiness_integrity": "test_persisted_engineering_readiness_expiry_supersession_and_integrity",
    "progress": "test_engineering_release_is_only_explicit_milestone_evidence",
    "forecast": "test_engineering_issue_date_is_explicit_forecast_input_and_approval_stays_frozen",
    "reads": "test_source_metrics_lookahead_history_are_read_only",
    "migration": "test_engineering_migration_single_head_and_postgresql_roundtrip",
}


def api_rows():
    path = ROOT / "backend/app/modules/engineering_foundation/router.py"
    tree = ast.parse(path.read_text("utf-8"))
    rows = []
    for item in tree.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in item.decorator_list:
            if (
                not isinstance(dec, ast.Call)
                or not isinstance(dec.func, ast.Attribute)
                or not dec.args
            ):
                continue
            method = dec.func.attr.upper()
            if method in {"GET", "POST", "PUT"} and isinstance(
                dec.args[0], ast.Constant
            ):
                route = dec.args[0].value
                rows.append(
                    [
                        method,
                        "/api/v1/engineering" + route,
                        item.name,
                        "ADMIN" if route.startswith("/admin") else "Proyecto",
                        "Lectura" if method == "GET" else "Comando",
                    ]
                )
    assert len(rows) == 39
    return rows


def build(source, evidence):
    gates = evidence["gate_status"]
    cases = {
        row["name"].split("[")[0]: row
        for row in evidence["postgresql"].get("cases", [])
    }

    def test_state(key):
        row = cases.get(TEST[key], {})
        if gates["postgresql"] == "STALE":
            return "STALE"
        return str(row.get("status", row.get("result", "PENDING"))).upper()

    def domain(rows):
        return [
            [
                control,
                function,
                TEST.get(ref, ref),
                test_state(ref)
                if ref in TEST
                else gates.get(ref, "REVISIÓN DE CÓDIGO"),
            ]
            for control, function, ref in rows
        ]

    specs = []

    def sheet(name, title, headers, rows, widths):
        specs.append(
            {
                "name": name,
                "title": title,
                "headers": headers,
                "rows": rows,
                "widths": widths,
            }
        )

    def controls(name, title, rows):
        sheet(
            name,
            title,
            ["Control", "Implementación o límite", "Evidencia", "Resultado"],
            domain(rows),
            [26, 52, 59, 23],
        )

    sections = re.findall(r"^#{1,2} (\d+)\. (.+)$", source, re.MULTILINE)
    assert [int(n) for n, _ in sections] == list(range(55))
    section_ref = {
        **dict.fromkeys([4, 5, 6, 32], "register"),
        **dict.fromkeys([8, 9, 10], "cde"),
        **dict.fromkeys([11, 12, 13], "reviews"),
        **dict.fromkeys([14, 15, 41], "ifc"),
        **dict.fromkeys([16, 17, 18, 42], "mappings"),
        19: "schedule",
        20: "forecast",
        21: "progress",
        **dict.fromkeys([23, 24, 25], "awp"),
        **dict.fromkeys([28, 29, 30], "reads"),
        31: "chromium_uat",
        36: "migration",
        38: "frontend",
        39: "postgresql",
        40: "postgresql",
        43: "postgresql",
        44: "postgresql",
        45: "chromium_uat",
        46: "performance",
        47: "preservation",
        50: "open_defects",
        51: "open_defects",
    }
    requirements = [
        [
            int(n),
            title,
            TEST.get(
                section_ref.get(int(n)),
                section_ref.get(int(n), "Diseño y alcance de O2A"),
            ),
            test_state(section_ref[int(n)])
            if section_ref.get(int(n)) in TEST
            else gates.get(section_ref.get(int(n)), "DOCUMENTADO"),
        ]
        for n, title in sections
    ]
    sheet(
        "01_Requirements",
        "Requisitos de Engineering Foundation",
        ["Sección", "Requisito", "Evidencia de referencia", "Resultado"],
        requirements,
        [12, 63, 59, 24],
    )
    controls(
        "02_Deliverables",
        "Registro y catálogos",
        [
            (
                "Registro",
                "Identidad, unicidad, tipo, disciplina y paginación",
                "register",
            ),
            (
                "Design Package",
                "Grupo técnico, distinto de EWP",
                "models.py / EngineeringDesignPackage",
            ),
            (
                "Configuración",
                "Tipos y disciplinas publicados en ADMIN",
                "chromium_uat",
            ),
            (
                "Interfaces",
                "Registro mínimo con referencia externa",
                "router.py / interfaces",
            ),
        ],
    )
    controls(
        "03_Revisions",
        "Revisiones y documentos",
        [
            ("Propósito", "Emitir para construcción no es liberar", "cde"),
            ("Adjunto CDE", "Identificador y SHA-256 sin duplicar el binario", "cde"),
            ("Sucesora", "Conserva revisión rechazada y linaje", "reject"),
            ("Historial", "Consulta sin efectos laterales", "reads"),
        ],
    )
    controls(
        "04_Reviews",
        "Revisión y aprobación",
        [
            ("Ronda", "Envío, inicio, aceptación y verificación", "reviews"),
            ("Comentarios", "Bloqueantes, respuesta, cierre y reenvío", "reviews"),
            ("Aprobación", "Actor independiente y revisión inmutable", "ifc"),
            ("Rechazo", "Decisión separada; no permite reescribir", "reject"),
        ],
    )
    controls(
        "05_IFC_Release",
        "Liberación IFC",
        [
            ("Comando IFC", "Motivo, fecha efectiva, referencia y actor", "ifc"),
            ("Integridad", "Snapshot inmutable y huella documental", "ifc"),
            ("Corte", "Sucesora futura no desplaza IFC vigente", "ifc"),
            ("Carga CDE", "Adjuntar no aprueba ni libera", "cde"),
        ],
    )
    controls(
        "06_EWP_Mappings",
        "Enlaces con paquetes AWP",
        [
            ("EWP", "Múltiples paquetes sin nueva autoridad AWP", "mappings"),
            ("CWA CWP IWP", "Identidad tipada y contexto del proyecto", "mappings"),
            ("Retiro", "Historial append-only con ETag de colección", "mappings"),
        ],
    )
    controls(
        "07_Scope_Plan",
        "Enlaces con Scope y Plan",
        [
            ("Scope", "ID canónico, sin copiar geometría o cantidad", "mappings"),
            ("Plan", "ID canónico, sin crear ni editar Plan Items", "mappings"),
            (
                "Ausencia de escritura",
                "Datos persistidos sin cambios",
                "progress",
            ),
        ],
    )
    controls(
        "08_Schedule",
        "Enlaces con el cronograma",
        [
            ("WBS y actividad", "Versión aceptada e ID externo exacto", "schedule"),
            (
                "Versión reemplazada",
                "Revisión o vínculo roto; no hay remapeo",
                "schedule",
            ),
            ("Fechas", "Forecast consume insumo explícito; P6 no cambia", "forecast"),
        ],
    )
    controls(
        "09_Readiness",
        "Evidencia de Engineering Readiness",
        [
            ("Cobertura", "Liberación vigente y referencia del paquete", "awp"),
            (
                "Vigencia",
                "Fecha de corte, sucesión, vencimiento e integridad",
                "readiness_integrity",
            ),
            ("Restricción", "No se cierra automáticamente; comando autorizado", "awp"),
            ("Release AWP", "READY no se convierte en RELEASED", "awp"),
        ],
    )
    controls(
        "10_Progress_Forecast",
        "Consumo por Progress y Forecast",
        [
            (
                "Progress",
                "Hito explícito, hash exacto y alcance correspondiente",
                "progress",
            ),
            (
                "Forecast",
                "Fecha y revisión explícitas; sin escritura automática",
                "forecast",
            ),
            (
                "Cost",
                "La referencia no cambia presupuesto, actual ni compromiso",
                "progress",
            ),
        ],
    )
    controls(
        "11_Admin_User",
        "Configuración y operación",
        [
            ("ADMIN", "Publicación de catálogos y política", "chromium_uat"),
            ("USER", "Navegación, registro y ciclo de Ingeniería", "chromium_uat"),
            ("Interfaz", "Comprobaciones estáticas y compilación", "frontend"),
        ],
    )
    controls(
        "12_Security",
        "Seguridad y auditoría",
        [
            ("RBAC", "Alcance por tenant, proyecto y acción", "register"),
            ("SoD", "Verificación, aprobación y emisión separadas", "reviews"),
            ("Concurrencia", "ETag e idempotencia", "register"),
            ("Inmutabilidad", "Triggers PostgreSQL y consultas de solo lectura", "ifc"),
            (
                "Perímetro",
                "No se reescriben App, visor ni migraciones anteriores",
                "protected_diff",
            ),
        ],
    )
    sheet(
        "13_API",
        "Operaciones HTTP de Ingeniería",
        ["Método", "Ruta", "Handler", "Ámbito", "Clase"],
        api_rows(),
        [13, 70, 42, 16, 16],
    )
    defect_rows = [
        [
            row["id"],
            row["severity"],
            row["status"],
            row.get("description", row.get("title", "")),
        ]
        for row in evidence["open_defects"].get("defects", [])
    ]
    defect_rows += [
        [
            "GATE-" + name.upper(),
            "—",
            value,
            " / ".join(result.get("errors", [])) or "Sin observaciones del recolector",
        ]
        for name, value in gates.items()
        if value != "PASS"
        for result in [
            evidence.get(
                name,
                evidence["browser"].get("uat" if name == "chromium_uat" else name, {}),
            )
        ]
    ]
    if not defect_rows:
        defect_rows = [
            [
                "O2A",
                "—",
                "CERRADO",
                "Sin defectos S1 o S2 abiertos según el registro revisado.",
            ]
        ]
    sheet(
        "14_Defects",
        "Defectos y comprobaciones pendientes",
        ["Referencia", "Severidad", "Estado", "Descripción"],
        defect_rows,
        [30, 14, 17, 88],
    )
    criteria = re.findall(
        r"^(.+?) = PASS$",
        source.split("# 50. RELEASE CRITERIA", 1)[1].split("# 51.", 1)[0],
        re.MULTILINE,
    )
    assert len(criteria) == 41
    release_rows = []
    proof_refs = (
        "ifc",
        "mappings",
        "protected_diff",
        "register",
        "reject",
        "ifc",
        "reviews",
        "reviews",
        "ifc",
        "cde",
        "ifc",
        "ifc",
        "mappings",
        "mappings",
        "mappings",
        "mappings",
        "schedule",
        "awp",
        "readiness_integrity",
        "awp",
        "awp",
        "progress",
        "schedule",
        "progress",
        "progress",
        "forecast",
        "cde",
        "chromium_uat",
        "register",
        "reviews",
        "register",
        "register",
        "reads",
        "postgresql",
        "chromium_uat",
        "preservation",
        "protected_diff",
        "protected_diff",
        "protected_diff",
        "open_defects",
        "open_defects",
    )
    for i, (criterion, key) in enumerate(zip(criteria, proof_refs, strict=True), 1):
        release_rows.append(
            [
                i,
                criterion,
                TEST.get(key, key),
                test_state(key) if key in TEST else gates[key],
            ]
        )
    sheet(
        "15_Release_Criteria",
        "Criterios de liberación de Wave O2A",
        ["N.º", "Criterio", "Comprobación", "Resultado"],
        release_rows,
        [9, 60, 59, 20],
    )
    assert len(specs) == 15
    return specs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, default=DEFAULT_SPEC, nargs="?")
    args = parser.parse_args()
    evidence = json.loads((QA / "release-evidence.json").read_text("utf-8-sig"))
    data = build(args.spec.read_text("utf-8-sig"), evidence)
    (QA / "traceability-data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(data)} sheets, {sum(len(item['rows']) for item in data)} records")


if __name__ == "__main__":
    main()
