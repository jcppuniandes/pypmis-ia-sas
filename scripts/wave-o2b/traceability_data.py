"""Produce traceability rows from implemented authorities and observed evidence."""

import json
import sys

from evidence import QA, ROOT, observations, suite_text

MODULE = "backend/app/modules/procurement_foundation/"
PROJECT = "/api/v1/procurement/projects/{workspace_id}"
PG = "test_procurement_o2b_release.py"
MATERIAL = "test_procurement_material_availability.py"
SOURCING = "test_procurement_sourcing_policy.py"

# Section numbers follow the supplied O2B PDF, not the order of implementation.
REQUIREMENTS = (
    (
        "Arquitectura",
        "Identidades operativas y autoridades externas separadas",
        "Procurement",
        "service.py",
        "/trace?package_id={package_id}",
        "pg",
        "La compra no duplica el proyecto ni la evidencia.",
    ),
    (
        "Autoridad",
        "No escribir hechos de Scope, Engineering, AWP, Schedule o finanzas",
        "Dominios de origen",
        "integration.py",
        "/source-facts",
        "pg",
        "Se comparan conteos protegidos en el caso crítico.",
    ),
    (
        "Alcance",
        "Fundación de compras, materiales, expediting y logística",
        "Procurement",
        "service.py",
        "/packages",
        "pg",
        "Ciclo de compra y material sintético.",
    ),
    (
        "Exclusiones",
        "Mantener O2C, ERP, pagos y liberación AWP fuera del incremento",
        "Dominios de origen",
        "docs/validation/wave-o2b/repository-reuse.md",
        "No aplica",
        "scope",
        "No se ejecutó despliegue productivo.",
    ),
    (
        "AWP",
        "Vincular PWP e IWP y exponer MATERIAL sin liberar paquetes",
        "AWP",
        "awp_provider.py",
        "/material-availability",
        "pg",
        "READY y NOT_RELEASED se verifican por separado.",
    ),
    (
        "Engineering",
        "Reusar liberaciones IFC y detectar fuentes sustituidas",
        "Engineering",
        "integration.py",
        "/mapping-targets",
        "pg",
        "Se rechazan hash inválido y fuente IFC sustituida.",
    ),
    (
        "Paquetes",
        "Planificar paquete, fechas y método de abastecimiento",
        "Procurement",
        "sourcing.py",
        "/packages",
        "pg",
        "Identidad separada de WorkPackage.",
    ),
    (
        "Requerimientos",
        "Registrar y activar requerimiento trazable",
        "Procurement",
        "sourcing.py",
        "/requirements",
        "pg",
        "Origen IFC cuando lo exige el perfil.",
    ),
    (
        "Requisición",
        "Someter y aprobar líneas por un actor independiente",
        "Procurement",
        "sourcing.py",
        "/requisitions",
        "pg",
        "Requisición distinta de RFQ.",
    ),
    (
        "RFQ",
        "Invitar proveedores, emitir y cerrar RFQ",
        "Procurement",
        "sourcing.py",
        "/rfqs",
        "pg",
        "Mínimo de proveedores publicado.",
    ),
    (
        "Proveedores",
        "Mantener identidad y estado del proveedor en el tenant",
        "Procurement",
        "sourcing.py",
        "/vendors",
        "pg",
        "Solo se usan proveedores elegibles.",
    ),
    (
        "Ofertas",
        "Registrar ofertas de proveedores invitados",
        "Procurement",
        "sourcing.py",
        "/bids",
        "pg",
        "Dos ofertas en la prueba crítica.",
    ),
    (
        "Evaluación",
        "Separar evaluación técnica de evaluación comercial",
        "Procurement",
        "sourcing.py",
        "/evaluations",
        "pg",
        "Se exige evaluación según política publicada.",
    ),
    (
        "Adjudicación",
        "Aprobar adjudicación con SoD y evaluación suficiente",
        "Procurement",
        "sourcing.py",
        "/awards",
        "pg",
        "La aprobación no emite una PO.",
    ),
    (
        "Orden operativa",
        "Crear, aprobar y emitir orden sin compromiso legado",
        "Procurement",
        "sourcing.py",
        "/purchase-orders",
        "pg",
        "PO sin adjudicación se bloquea cuando aplica.",
    ),
    (
        "Revisión de PO",
        "Aprobar sucesor sin editar líneas originales",
        "Procurement",
        "sourcing.py",
        "/purchase-orders/{identity}/revisions",
        "policy",
        "Prueba focalizada y guardia de PostgreSQL.",
    ),
    (
        "Demanda material",
        "Derivar cantidad y unidad de la necesidad de compra",
        "Procurement",
        "materials.py",
        "/material-requirements",
        "pg",
        "La demanda enlaza el paquete de ejecución.",
    ),
    (
        "Ítems",
        "Catalogar material por proyecto y unidad",
        "Procurement",
        "materials.py",
        "/material-items",
        "pg",
        "No se registra inventario ERP.",
    ),
    (
        "Disponibilidad",
        "Calcular cobertura aceptada, reservada y vigente",
        "Procurement",
        "availability.py",
        "/material-availability",
        "pg",
        "Recibido o rechazado no aporta cobertura.",
    ),
    (
        "Asignación",
        "Reservar solo saldo aceptado para un paquete elegible",
        "Procurement",
        "materials.py",
        "/material-allocations",
        "pg",
        "El rechazo y la cuarentena no son asignables.",
    ),
    (
        "Expediting",
        "Guardar hitos y eventos con fechas y respaldo",
        "Procurement",
        "materials.py",
        "/expediting-events",
        "pg",
        "El hito no equivale a inspección.",
    ),
    (
        "Inspección",
        "Separar planificación y decisión de inspección",
        "Procurement",
        "materials.py",
        "/inspections",
        "pg",
        "La política puede bloquear el despacho.",
    ),
    (
        "Embarque",
        "Registrar despacho, tránsito y llegada con sus líneas",
        "Procurement",
        "materials.py",
        "/shipments",
        "pg",
        "ARRIVED no crea recepción.",
    ),
    (
        "Recepción",
        "Validar recepción y disposición de calidad por separado",
        "Procurement",
        "materials.py",
        "/material-receipts",
        "pg",
        "Control de cantidades y recepción excesiva.",
    ),
    (
        "Schedule",
        "Referenciar WBS, actividad o hito por versión y clave P6",
        "Schedule",
        "integration.py",
        "/mapping-targets",
        "pg",
        "No se remapea por nombre.",
    ),
    (
        "Cost",
        "Exponer adjudicación y PO como candidatos de solo lectura",
        "Cost",
        "integration.py",
        "/source-facts?package_id={package_id}",
        "partial",
        "No se demostró adopción gobernada por Cost.",
    ),
    (
        "Progress",
        "Exponer hechos físicos sin registrar avance",
        "Progress",
        "integration.py",
        "/source-facts?package_id={package_id}",
        "partial",
        "No se demostró adopción gobernada por Progress.",
    ),
    (
        "Forecast",
        "Exponer pronósticos de entrega sin publicar forecast",
        "Forecast",
        "integration.py",
        "/source-facts?package_id={package_id}",
        "partial",
        "No se demostró adopción gobernada por Forecast.",
    ),
    (
        "CDE",
        "Vincular documento, adjunto y huella sin duplicar binarios",
        "CDE",
        "integration.py",
        "/document-targets",
        "pg",
        "Acceso documental conserva pertenencia al proyecto.",
    ),
    (
        "ADMIN y USER",
        "Publicar política independiente y operar en proyecto autorizado",
        "Tenant y proyecto",
        "profiles.py",
        "/configuration",
        "browser",
        "Creación y publicación con actores independientes.",
    ),
    (
        "Seguridad",
        "Aislar tenant, proyecto y acciones por rol",
        "Seguridad",
        "service.py",
        "/packages",
        "pg",
        "Incluye alcance, ETag e idempotencia.",
    ),
    (
        "SoD",
        "Separar decisiones incompatibles de compras y calidad",
        "Seguridad",
        "policy.py",
        "/requisitions/{identity}/actions",
        "pg",
        "Los permisos no eliminan la comprobación de actor.",
    ),
    (
        "Auditoría",
        "Conservar hechos, auditoría, versiones y linaje",
        "Procurement",
        "migration_0077_ddl.py",
        "/history",
        "pg",
        "Pruebas de rechazo de sobrescritura por SQL.",
    ),
    (
        "Modelo",
        "Guardar entidades diferenciadas e integridad SQL",
        "Procurement",
        "migration_0077_ddl.py",
        "No aplica",
        "migration",
        "27 tablas; el perfil usa el catálogo existente.",
    ),
    (
        "API",
        "Exponer consultas y comandos versionados",
        "Procurement",
        "router.py",
        "/api/v1/procurement",
        "pg",
        "Inventario por método y ruta en 13_API.",
    ),
    (
        "Web",
        "Montar Procurement Manager y configuración ADMIN",
        "Procurement",
        "frontend/src/features/procurement-foundation/",
        "/workspaces/{id}/procurement",
        "browser",
        "La prueba usa navegador, API y PostgreSQL reales.",
    ),
    (
        "Look-Ahead",
        "Consultar hitos por horizonte y contexto de ejecución",
        "Procurement",
        "integration.py",
        "/lookahead",
        "pg",
        "La salida es una proyección de Procurement.",
    ),
    (
        "Readiness",
        "Explicar preparación y vínculos sin sustituir AWP",
        "Procurement",
        "integration.py",
        "/readiness",
        "pg",
        "Material READY no implica IWP liberado.",
    ),
    (
        "Trazabilidad",
        "Seguir demanda, compra, logística y material",
        "Procurement",
        "integration.py",
        "/trace?package_id={package_id}",
        "pg",
        "El caso prueba el encadenamiento de IDs.",
    ),
    (
        "Caso crítico",
        "Completar demanda a IWP con AWP sin liberar",
        "Procurement y AWP",
        "backend/tests/procurement_release_fixture.py",
        "/material-availability",
        "pg",
        "Fixture independiente de Proyecto 14.",
    ),
    (
        "Negativos",
        "Rechazar accesos, fuentes, cantidades y estados inválidos",
        "Procurement y seguridad",
        "backend/tests/test_procurement_o2b_release.py",
        "/api/v1/procurement",
        "pg",
        "HTTP y SQL en PostgreSQL dedicado.",
    ),
    (
        "Regresión",
        "Ejecutar regresión O1, Engineering y autoridades consumidoras",
        "Validación",
        "backend/tests/",
        "No aplica",
        "regression",
        "No equivale a repetir todas las UAT históricas.",
    ),
    (
        "Proyecto 14",
        "Comparar huellas y referencias en solo lectura",
        "Proyecto",
        "scripts/wave-o2b/capture_preservation.py",
        "No aplica",
        "preservation",
        "La fila legacy no existe; el workspace canónico se preservó.",
    ),
    (
        "Migración",
        "Subir, revertir y volver a subir en PostgreSQL vacío",
        "Alembic",
        "backend/alembic/versions/20261111_0077_procurement_foundation.py",
        "No aplica",
        "migration",
        "Sin cambios en la base habitual.",
    ),
    (
        "Pruebas",
        "Separar política, HTTP, SQL, migración y navegador",
        "Validación",
        "backend/tests/test_procurement_o2b_release.py",
        "No aplica",
        "partial",
        "El número de casos no es el número de ciclos completos.",
    ),
    (
        "Chromium",
        "Ejecutar el recorrido completo y conservar evidencia",
        "Validación",
        "frontend/e2e/procurement-foundation.spec.ts",
        "/workspaces/{id}/procurement",
        "browser",
        "No se consideran mocks como evidencia.",
    ),
    (
        "Rendimiento",
        "Medir ocho operaciones con tres muestras y tamaño",
        "Validación",
        "frontend/e2e/procurement-foundation.spec.ts",
        "Ocho rutas de lectura",
        "performance",
        "Resultado local sin SLA.",
    ),
    (
        "Matriz",
        "Entregar trazabilidad en 17 hojas",
        "Documentación",
        "scripts/wave-o2b/traceability_data.py",
        "No aplica",
        "artifact",
        "Requisitos por sección del PDF.",
    ),
    (
        "Informe",
        "Entregar informe técnico de 39 secciones en Word",
        "Documentación",
        "scripts/wave-o2b/generate_report.py",
        "No aplica",
        "artifact",
        "El informe recoge evidencia y brechas.",
    ),
    (
        "Criterios",
        "Demostrar separaciones, autoridades y ausencia de defectos críticos",
        "Gobernanza",
        "docs/validation/wave-o2b/",
        "No aplica",
        "pending",
        "La cobertura parcial no autoriza la liberación.",
    ),
    (
        "Decisión",
        "Emitir marcadores solo con verificación integral",
        "Gobernanza",
        "scripts/wave-o2b/evidence.py",
        "No aplica",
        "pending",
        "No se emiten los marcadores de cierre.",
    ),
    (
        "Ejecución",
        "Implementar, probar y conservar la evidencia del incremento",
        "Gobernanza",
        "docs/validation/wave-o2b/",
        "No aplica",
        "partial",
        "El siguiente incremento depende del cierre de estas brechas.",
    ),
)


def main():
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app
    from app.modules.procurement_foundation.migration_0077_ddl import TABLES
    from app.modules.procurement_foundation.permissions import ROLE_ACTIONS
    from app.modules.procurement_foundation.policy import DEFAULT_PROFILE, TRANSITIONS

    e = observations()
    good = lambda result: bool(
        result
        and result["passed"]
        and not (result["failed"] or result["error"] or result["skipped"])
    )
    pg = good(e["critical_case"])
    mig = good(e["migration"])
    uat = e["browser_result"] == "PASS"
    perf = len(e["operations"]) == 8 and all(
        len(row["samples_ms"]) >= 3 for row in e["operations"]
    )
    proof = {
        "pg": (
            PG,
            "Caso crítico HTTP y SQL aprobado" if pg else "Sin aprobación final",
            "Verificado" if pg else "Pendiente",
        ),
        "migration": (
            "test_procurement_o2b_migration.py",
            e["migration_text"],
            "Verificado" if mig else "Parcial",
        ),
        "policy": (
            SOURCING,
            suite_text(e["sourcing_cases"]),
            "Verificado" if good(e["sourcing_cases"]) else "Pendiente",
        ),
        "scope": (
            "repository-reuse.md",
            "Perímetro de cambios y autoridades",
            "Verificado",
        ),
        "regression": ("Suites O1 y O2A", e["regression_text"], "Parcial"),
        "preservation": (
            "capture_preservation.py",
            "Comparación antes y después",
            "Verificado" if e["preserved"] else "Pendiente",
        ),
        "browser": (
            "procurement-foundation.spec.ts",
            e["browser_text"],
            "Verificado" if uat else "Pendiente",
        ),
        "performance": (
            "procurement-foundation.spec.ts",
            e["performance_text"],
            "Verificado" if perf else "Pendiente",
        ),
        "partial": (PG, "Implementación revisada; evidencia parcial", "Parcial"),
        "pending": ("Criterios §50–51", "No se acreditó cierre integral", "Pendiente"),
        "artifact": ("Entregable nativo", "Informe Word o matriz Excel", "Entregado"),
    }
    specs = []

    def tab(name, title, headers, widths, rows):
        assert rows and all(len(row) == len(headers) for row in rows)
        specs.append(
            {
                "name": name,
                "title": title,
                "headers": headers,
                "widths": widths,
                "rows": rows,
            }
        )

    tab(
        "00_README",
        "Trazabilidad de la Wave O2B",
        ["Elemento", "Alcance"],
        [28, 92],
        [
            ["Decisión", e["decision"]],
            [
                "Base",
                "P&Pmis Construction AI. Revisión e5747a6; Alembic 20261109_0076.",
            ],
            [
                "Fuente",
                "P&Pmis Wave O2B Procurement Materials Logistics Prompt Codex, secciones 1 a 52.",
            ],
            [
                "Lectura",
                "Verificado indica evidencia ejecutada. Parcial indica alcance o comprobación incompleta. Pendiente indica un cierre no demostrado.",
            ],
            [
                "Perímetro",
                "Bases aisladas y datos sintéticos. Proyecto 14 solo se observó en modo lectura. No se desplegó a producción.",
            ],
        ],
    )
    req = []
    for i, (domain, description, owner, code, route, kind, note) in enumerate(
        REQUIREMENTS, 1
    ):
        test, evidence, status = proof[kind]
        code = MODULE + code if "/" not in code else code
        route = (
            PROJECT + route
            if route.startswith("/") and not route.startswith(("/api/", "/workspaces/"))
            else route
        )
        req.append(
            [
                f"O2B-{i:02}",
                domain,
                description,
                owner,
                code,
                route,
                test,
                evidence,
                status,
                note,
            ]
        )
    assert len(req) == 52
    tab(
        "01_REQUIREMENTS",
        "Requisitos y evidencia por sección",
        [
            "ID",
            "Dominio",
            "Descripción",
            "Autoridad",
            "Implementación",
            "API",
            "Prueba",
            "Evidencia",
            "Estado",
            "Observaciones",
        ],
        [14, 20, 47, 22, 52, 49, 38, 48, 16, 52],
        req,
    )
    tab(
        "02_AUTHORITY",
        "Autoridades y límites de escritura",
        ["Dominio", "Conserva", "Consumo de O2B"],
        [23, 53, 57],
        [
            [
                "Procurement",
                "Demanda, compra operativa y hechos físicos",
                "Gobierna las nuevas transacciones.",
            ],
            [
                "AWP",
                "Paquetes y liberación",
                "Lee identidad de paquete; entrega evidencia MATERIAL.",
            ],
            [
                "Engineering",
                "Revisiones, entregables e IFC",
                "Vínculos con identidad y huella.",
            ],
            ["CDE", "Documento y adjunto", "Solo conserva referencias."],
            [
                "Scope y Plan",
                "Alcance, cantidades y planificación",
                "Lee identificadores vigentes.",
            ],
            ["Schedule", "Cronograma aceptado", "Lee versión y clave externa."],
            [
                "Cost",
                "Compromisos y costos reales",
                "Publica candidatos sin asiento financiero.",
            ],
            [
                "Progress",
                "Medición aprobada",
                "Publica hechos físicos sin cantidad instalada.",
            ],
            [
                "Forecast",
                "Proyección aprobada",
                "Publica señales, no un pronóstico aprobado.",
            ],
        ],
    )
    model_rows = [
        [row[0], "20261111_0077", "Append-only o transiciones protegidas según entidad"]
        for row in TABLES
    ]
    assert len(model_rows) == 27
    tab(
        "03_DOMAIN_MODEL",
        "Inventario de tablas O2B",
        ["Tabla PostgreSQL", "Revisión", "Integridad"],
        [48, 15, 63],
        model_rows,
    )
    tab(
        "04_WORKFLOWS",
        "Secuencia de decisiones y hechos",
        ["Paso", "Entrada", "Salida", "Control"],
        [22, 38, 37, 57],
        [
            [
                "Planificación",
                "Paquete y requerimiento",
                "Requisición aprobada",
                "Aprobador distinto del preparador.",
            ],
            [
                "Competencia",
                "RFQ y dos invitaciones",
                "Ofertas recibidas",
                "Solo proveedores elegibles.",
            ],
            [
                "Selección",
                "Evaluaciones técnica y comercial",
                "Adjudicación aprobada",
                "Evaluador no adjudica cuando el perfil lo exige.",
            ],
            [
                "Orden",
                "Adjudicación y líneas",
                "PO aprobada y emitida",
                "Una modificación exige una revisión sucesora.",
            ],
            [
                "Logística",
                "Línea de PO e inspección",
                "Embarque y recepción",
                "Llegada y recepción son hechos diferentes.",
            ],
            [
                "Disponibilidad",
                "Aceptación y asignación a IWP",
                "Cobertura MATERIAL",
                "AWP mantiene la autoridad de liberación.",
            ],
        ],
    )
    statuses = [
        [entity, action, ", ".join(sorted(prior)), next_state]
        for entity, actions in TRANSITIONS.items()
        for action, (prior, next_state) in actions.items()
    ]
    statuses += [
        ["Material", "evaluar", "Hechos a la fecha de corte", "READY o diagnóstico"],
        ["AWP", "evaluar MATERIAL", "NOT_RELEASED", "NOT_RELEASED"],
    ]
    tab(
        "05_STATUSES",
        "Transiciones de estado",
        ["Entidad", "Acción", "Origen", "Destino"],
        [27, 27, 43, 32],
        statuses,
    )
    tab(
        "06_PERMISSIONS",
        "Roles y permisos registrados",
        ["Rol", "Acciones procurement", "Límite"],
        [45, 80, 55],
        [
            [
                role,
                ", ".join(sorted(actions))
                if len(actions) < 15
                else f"{len(actions)} acciones; ver permissions.py",
                "No asigna usuarios automáticamente.",
            ]
            for role, actions in ROLE_ACTIONS.items()
        ],
    )
    tab(
        "07_SOD",
        "Segregación de funciones por defecto",
        ["Regla publicada", "Valor inicial", "Aplicación"],
        [52, 16, 58],
        [
            [
                key,
                value,
                "Se verifica en el comando del actor. El perfil no concede permisos.",
            ]
            for key, value in DEFAULT_PROFILE["separation_of_duties"].items()
        ],
    )
    tab(
        "08_INTEGRATIONS",
        "Orígenes y consumidores de solo lectura",
        ["Integración", "Límite", "Implementación"],
        [25, 66, 39],
        [
            [row[0], row[2], "integration.py" if row[0] != "AWP" else "awp_provider.py"]
            for row in specs[2]["rows"][1:]
        ],
    )
    for name, title, rows in (
        (
            "09_AWP_TRACEABILITY",
            "Vínculos AWP y evidencia MATERIAL",
            [
                [
                    "Paquete Procurement",
                    "PWP",
                    "Enlace canónico; identidades separadas.",
                ],
                [
                    "Demanda de material",
                    "CWP o IWP",
                    "Validación del paquete objetivo y vigencia.",
                ],
                [
                    "Asignación vigente",
                    "Readiness MATERIAL",
                    "Se conserva hash; no cambia release_state.",
                ],
            ],
        ),
        (
            "10_ENGINEERING_TRACEABILITY",
            "Trazabilidad de Engineering y CDE",
            [
                ["Requerimiento", "IFC_RELEASE", "IFC efectivo y huella exacta."],
                [
                    "Referencia sustituida",
                    "Revisión Engineering",
                    "Obliga revisar; no cambia Engineering.",
                ],
                [
                    "Evidencia documental",
                    "CDE",
                    "Documento y adjunto existentes; acceso verificado.",
                ],
            ],
        ),
        (
            "11_SCHEDULE_TRACEABILITY",
            "Trazabilidad de cronograma",
            [
                [
                    "Enlace WBS",
                    "ScheduleVersion y external_id",
                    "Se conserva el ID externo exacto.",
                ],
                [
                    "Actividad o hito",
                    "Versión aceptada",
                    "Fuente ausente o sustituida exige revisión.",
                ],
                [
                    "Look-Ahead",
                    "Proyección operativa",
                    "No modifica fechas ni calcula CPM.",
                ],
            ],
        ),
        (
            "12_COST_TRACEABILITY",
            "Límites con Cost y otros consumidores",
            [
                [
                    "Adjudicación y PO",
                    "Cost",
                    "Candidatos; no crean compromiso ni costo real.",
                ],
                [
                    "CBS y cuenta",
                    "Cost Foundation",
                    "Identidades canónicas sin escritura presupuestal.",
                ],
                [
                    "Recepción y aceptación",
                    "Progress",
                    "Hechos físicos; no registran instalado.",
                ],
                [
                    "Pronóstico de entrega",
                    "Forecast",
                    "Señal de fecha; no publica un forecast.",
                ],
            ],
        ),
    ):
        tab(name, title, ["Origen", "Destino", "Control"], [36, 39, 69], rows)
    openapi = app.openapi()["paths"]
    api = [
        [
            method.upper(),
            route,
            operation.get("summary", ""),
            "Lectura" if method == "get" else "Comando",
        ]
        for route, methods in sorted(openapi.items())
        if route.startswith("/api/v1/procurement")
        for method, operation in sorted(methods.items())
        if method in {"get", "post", "patch", "put", "delete"}
    ]
    tab(
        "13_API",
        "Inventario OpenAPI de Procurement",
        ["Método", "Ruta", "Operación", "Tipo"],
        [13, 92, 46, 16],
        api,
    )
    tests = [
        [
            "Caso crítico HTTP y SQL",
            PG,
            suite_text(e["critical_case"]),
            "PostgreSQL aislado",
        ],
        [
            "Disponibilidad",
            MATERIAL,
            suite_text(e["material_cases"]),
            "No equivale al caso transaccional",
        ],
        [
            "Sourcing",
            SOURCING,
            suite_text(e["sourcing_cases"]),
            "SQLite en memoria",
        ],
        [
            "Migración",
            "test_procurement_o2b_migration.py",
            e["migration_text"],
            "PostgreSQL vacío",
        ],
        [
            "Regresión O2A",
            "Suites de Engineering y consumidores",
            suite_text(e["regression"]),
            "PostgreSQL y políticas",
        ],
        [
            "Regresión O1",
            "Suites operacionales",
            suite_text(e["additional"]),
            "PostgreSQL y políticas",
        ],
        [
            "Chromium",
            "procurement-foundation.spec.ts",
            e["browser_text"],
            "Navegador real",
        ],
    ]
    tests += [
        [
            row["operation"],
            "Lectura HTTP desde UAT",
            f"Mediana {row['median_ms']:.1f} ms",
            f"Filas: {row.get('record_count', 'n/d')}. Bytes JSON: {row.get('response_json_bytes', 'n/d')}.",
        ]
        for row in e["operations"]
    ]
    tab(
        "14_TESTS",
        "Pruebas y mediciones locales",
        ["Grupo", "Caso o suite", "Resultado", "Entorno o tamaño"],
        [34, 52, 81, 45],
        tests,
    )
    tab(
        "15_DEFECTS",
        "Brechas de comprobación",
        ["ID", "Hallazgo", "Estado"],
        [16, 96, 21],
        [[f"O2B-G{i:02}", gap, "Pendiente"] for i, gap in enumerate(e["gaps"], 1)],
    )
    tab(
        "16_RELEASE_CRITERIA",
        "Criterios para decidir la liberación",
        ["Criterio", "Evidencia", "Estado"],
        [52, 69, 18],
        [
            [
                "Identidades y decisiones separadas",
                PG,
                "Verificado" if pg else "Pendiente",
            ],
            [
                "Ida y vuelta de 0077",
                e["migration_text"],
                "Verificado" if mig else "Parcial",
            ],
            [
                "Proyecto 14 preservado",
                "Huellas antes y después",
                "Verificado" if e["preserved"] else "Pendiente",
            ],
            [
                "Chromium en pila real",
                e["browser_text"],
                "Verificado" if uat else "Pendiente",
            ],
            [
                "Ocho lecturas con tres muestras",
                e["performance_text"],
                "Verificado" if perf else "Pendiente",
            ],
            [
                "Regresión completa y adopción de consumidores",
                "Consultar 14_TESTS y 15_DEFECTS",
                "Parcial",
            ],
            ["Liberación O2B y recomendación O2C", e["decision"], "Pendiente"],
        ],
    )
    assert len(specs) == 17
    (QA / "traceability-data.json").write_text(
        json.dumps(specs, ensure_ascii=False, indent=2), "utf-8"
    )
    print(f"{len(specs)} hojas, {len(req)} requisitos, {len(api)} operaciones OpenAPI")


if __name__ == "__main__":
    main()
