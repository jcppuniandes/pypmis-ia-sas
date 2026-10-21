"""Build architecture documentation data; never imports or executes the product."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs/architecture/operational"
AUDIT = ROOT / "docs/validation/operational-master-architecture-20261019"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_OPERATIONAL_MACROPROCESS_MASTER_ARCHITECTURE_DOMAIN_MAP_IMPLEMENTATION_ROADMAP.md"
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def cell(value):
    if isinstance(value, dict):
        return "\n".join(f"{key}: {cell(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "\n".join(cell(item) for item in value)
    return str(value) if value is not None else ""


def sheet(name, title, headers, rows, widths=None):
    return {
        "name": name,
        "title": title,
        "headers": headers,
        "rows": rows,
        "widths": widths or [16] + [36] * (len(headers) - 1),
        "source_note": "Corte 19 oct 2026 · Inspección estática; propuestas no aprobadas ni desplegadas. Referencias path:line locales.",
    }


def main():
    data = read(DESIGN / "domain-design.json")
    contracts = read(DESIGN / "control-contracts.json")
    backend = read(AUDIT / "backend-inventory.json")
    frontend = read(AUDIT / "frontend-inventory.json")
    procurement = read(AUDIT / "procurement-handoff-inventory.json")
    domains = data["domains"]
    criteria = [
        item["key"] if isinstance(item, dict) else item
        for item in data["scoring_method"]["criteria"]
    ]
    weights = [0.15, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.05, 0.05, 0.05, 0.05]
    labels = [
        "Valor de negocio",
        "Centralidad",
        "Reutilización",
        "Complejidad",
        "Riesgo del modelo",
        "Acoplamiento",
        "Integración estratégica",
        "Aplicabilidad Owner",
        "Aplicabilidad Contractor",
        "Valor de reporting",
        "Urgencia declarada",
    ]
    rationale = [
        "Impacto transversal estimado, no ROI.",
        "Prerrequisitos/consumidores del grafo.",
        "Evidencia reutilizable localizada.",
        "Penaliza esfuerzo relativo.",
        "Penaliza exposición de identidad/autoridad.",
        "Penaliza contratos interdependientes.",
        "Relevancia de la frontera estratégica.",
        "Cobertura del modelo Owner.",
        "Cobertura del modelo Contractor.",
        "Transparencia y decisiones de control.",
        "3 neutral para todos: no se declaró urgencia relativa.",
    ]
    scoring = {
        "sheet": "09_Wave_Prioritization",
        "status": "PROPOSED_ARCHITECTURAL_JUDGMENT_NOT_BUSINESS_APPROVAL",
        "explanation": "Pesos propuestos para discusión, no aprobados por negocio. Los prerrequisitos de seguridad/identidad y el DAG prevalecen sobre el ranking. 1–5; mayor complejidad/riesgo/acoplamiento penaliza. La urgencia se mantiene neutral en 3.",
        "criteria": [
            {
                "key": key,
                "label": label,
                "weight": weight,
                "direction": "penalty" if 3 <= i <= 5 else "benefit",
                "rationale": why,
            }
            for i, (key, label, weight, why) in enumerate(
                zip(criteria, labels, weights, rationale)
            )
        ],
        "rows": [],
    }
    for domain in domains:
        domain.pop("architectural_signal_score", None)
        degree = len(domain["upstream_ids"]) + len(domain["downstream_ids"])
        domain["scores"]["dependency_centrality"]["rationale"] = (
            f"Juicio de centralidad: {len(domain['upstream_ids'])} fuentes y {len(domain['downstream_ids'])} consumidores declarados ({degree} conexiones); no mide popularidad ni prioridad aprobada."
        )
        domain["scores"]["cross_domain_coupling"]["rationale"] = (
            f"Exposición de contratos con {len(domain['upstream_ids'])} fuentes y {len(domain['downstream_ids'])} consumidores; no se interpreta como acoplamiento de tablas autorizado."
        )
        scoring["rows"].append(
            {
                "domain_id": domain["id"],
                "domain_name": domain["name"],
                "scores": {key: domain["scores"][key]["score"] for key in criteria},
                "rationale": cell(
                    [f"{key}: {domain['scores'][key]['rationale']}" for key in criteria]
                ),
                "source_refs": cell(domain["source_refs"]),
                "wave_proposed": domain["wave"],
            }
        )
    # One scoring definition across every artifact; remove the optional alternative.
    data["scoring_method"] = {
        key: value for key, value in scoring.items() if key != "rows"
    }
    (DESIGN / "domain-design.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    capabilities = []
    for row in backend["components"]:
        refs = [
            value
            for key, value in row.items()
            if "evidence" in key or key in ("models", "api")
        ]
        capabilities.append(
            [
                row["id"],
                "BACKEND",
                row["domain"],
                row["classification"],
                row["maturity"],
                row.get("behavior", row["maturity"]),
                cell(row["limits"]),
                row.get(
                    "ownership_recommendation",
                    row.get(
                        "authority_boundary",
                        "Ver autoridad propuesta del dominio D01–D25; no nuevo maestro.",
                    ),
                ),
                cell(refs),
                cell(row.get("test_coverage", [])),
                "SOURCE_INSPECTED_ONLY / NOT_RUN",
            ]
        )
    for row in frontend["candidates"]:
        capabilities.append(
            [
                row["id"],
                "FRONTEND",
                row["candidate"],
                row["frontend_status"],
                cell(row.get("current_views", [])),
                row["observation"],
                "No prueba de navegación ejecutada en este incremento.",
                row["proposed_action"],
                cell(row["evidence"]),
                cell(row.get("test_definitions", [])),
                "SOURCE_INSPECTED_ONLY / NOT_RUN",
            ]
        )
    for row in procurement["capabilities"]:
        capabilities.append(
            [
                row["id"],
                "PROCUREMENT / HANDOFF",
                row["name"],
                row["inventory_classification"],
                row["current_state"],
                row["procurement_boundary"],
                "No flujo ejecutado ni datos de negocio modificados.",
                row["future_owner"],
                cell(row["evidence"]),
                "",
                "SOURCE_INSPECTED_ONLY / NOT_RUN",
            ]
        )
    legacy = []
    for i, row in enumerate(backend["orphan_review"], 1):
        legacy.append(
            [
                f"LEG-BE-{i:02d}",
                row["candidate"],
                row["decision"],
                row["reason"],
                cell(row["evidence"]),
                "No eliminado",
                "Revisión de consumidores externos/paridad/deprecación antes de cualquier limpieza.",
            ]
        )
    for row in frontend["cleanup_candidates"]:
        legacy.append(
            [
                row["id"],
                cell(row["paths"]),
                row["classification"],
                row["reason"],
                row["evidence"],
                "No eliminado",
                "Validar rutas, uso, compatibilidad y paridad antes de deprecar.",
            ]
        )
    for row in procurement["capabilities"]:
        legacy.append(
            [
                "LEG-" + row["id"],
                row["name"],
                row["legacy_disposition"],
                row["current_state"],
                cell(row["evidence"]),
                "No eliminado",
                row["procurement_boundary"],
            ]
        )

    gap_specs = [
        (
            "P0",
            "Identidad canónica / legacy",
            "enterprise_workspaces y projects son espacios de ID distintos. Creación canónica no crea Project legacy.",
            "Binding explícito tenant-scoped, único y versionado; rechazo de ausente/ambiguo, membresía/estado/autorización vigentes.",
            "O1A",
            "backend/tests/test_project_creation_process.py:642",
            "No asumir igualdad de ID/nombre; no crear segundo maestro.",
        ),
        (
            "P0",
            "Condiciones para comprometer",
            "ACTIVE no demuestra autorización de compromiso; Post-FID distingue activation-blocking y commitment-only.",
            "Cada comando de obligación consulta autoridad/condiciones actuales antes de promover.",
            "O1A / O2",
            "backend/app/modules/post_fid_governance/service.py:492",
            "No resolver condiciones estratégicas localmente.",
        ),
        (
            "P0",
            "Presupuesto con múltiples escritores",
            "Ingestión schedule y BP-CBS-WBS materializan Budget/CostCode fuera de una autoridad uniforme.",
            "Cost único escritor mediante comando aprobado; adaptadores emiten propuestas.",
            "O1B",
            "backend/app/services/schedule_ingestion.py:1176",
            "Conservar datos/historial; migración posterior acotada y autorizada.",
        ),
        (
            "P0",
            "Baselines inmutables",
            "Campos baseline se actualizan durante ingestión legacy.",
            "Original/aprobada/current/update/forecast separados; aceptación de importación no aprueba baseline.",
            "O1B",
            "backend/app/services/schedule_ingestion.py:1612",
            "Nunca sobrescribir aprobación histórica.",
        ),
        (
            "P0",
            "Compromisos / actual / accrual",
            "Agregación Contract + PO y committed + executed sin semántica neta uniforme localizada.",
            "INCLUDED/CALL_OFF/ADDITIVE, liquidación y clave de origen económico; reversión accrual/actual.",
            "O1B contrato mínimo / O2",
            "backend/app/services/integrated_control.py:392",
            "Riesgo de diseño; no se afirma doble conteo de importes reales.",
        ),
        (
            "P1",
            "P6 calendario/unidades",
            "Fallback critical por float y conversión horas/8 no constituyen fidelidad P6 completa.",
            "Conservar fechas/critical/float/calendarios/unidades importadas; bloquear conversión desconocida.",
            "O1B",
            "backend/app/services/schedule_ingestion.py:1731",
            "P6 calcula CPM; no CPM operacional nativo.",
        ),
        (
            "P1",
            "P6 ciclo de intercambio",
            "XML/XER importados; exportador completo con roundtrip no demostrado.",
            "Subset soportado explícito; staging/diff/revisión/promoción/rollback. XML para intercambio de baseline; XER requiere vínculo separado.",
            "O1B",
            "backend/app/services/schedule_ingestion.py:402",
            "No API/OPC/direct sync ni promesa de exportación existente.",
        ),
        (
            "P1",
            "Scope y BIM/APU",
            "Asignación BIM/APU en raw_data no es publicación de presupuesto Cost.",
            "Scope Item/revisión/cantidad/método/unidad y mappings M:N con aprobación de fuente.",
            "O1B",
            "backend/app/api/v1/routers/projects.py:1165",
            "Reutilizar GUID/ExpressID/hash/lineage sin nuevo maestro BIM.",
        ),
        (
            "P1",
            "Progress tipado",
            "Capturas/registros reales pero ciclo método-aprobación-corte incompleto.",
            "Distinguir físico/schedule/costo/earned/cantidad/weighted/milestone, denominador y aprobación.",
            "O1B",
            "backend/app/domain/models.py:685",
            "No promediar porcentajes de métodos distintos.",
        ),
        (
            "P1",
            "Período común",
            "Snapshots/reportes no demuestran cierre y freeze de todas las fuentes.",
            "OPEN → REVIEW → CLOSED → PUBLISHED, ajuste/reapertura versionada y data date explícito.",
            "O1A / O1C",
            "backend/app/domain/models.py:1234",
            "No calendario independiente por módulo.",
        ),
        (
            "P1",
            "Forecast gobernado",
            "Fórmulas CPI/SPI heurísticas no equivalen a forecast aprobado y versionado.",
            "ETC bottom-up/estadístico declarado, EAC=actual reconocido+ETC, contingencia/reservas una sola vez.",
            "O1C",
            "backend/app/services/control_core.py:221",
            "Ningún forecast cambia baseline o autorización de inversión.",
        ),
        (
            "P1",
            "Dashboard con efectos",
            "GET dashboard puede producir KPI/snapshots/forecast cuando faltan.",
            "Consultas de reporting sin escrituras transaccionales; publicación explícita del snapshot.",
            "O1C",
            "backend/app/services/control_core.py:27",
            "No se ejecutó GET en esta auditoría.",
        ),
        (
            "P1",
            "Risk / Issue / Change",
            "Menús reservados no son registro operacional completo; ChangeRequest parcial.",
            "Riesgo incierto, issue ocurrido y change con assessments, aprobación e implementación separadas.",
            "O1B",
            "frontend/src/navigation/applicationNavigation.ts:626",
            "No duplicar riesgo estratégico/QRA ni sustituir NCR/claims.",
        ),
        (
            "P1",
            "Procurement UI / autoridad",
            "RFQ/Contract/PO backend parciales; varias pantallas reservadas.",
            "Sourcing/recomendación en Procurement, obligación única en Contract Administration.",
            "O2",
            "frontend/src/navigation/applicationNavigation.ts:354",
            "Vendors/Partners compartidos; Funds conserva gobierno estratégico.",
        ),
        (
            "P2",
            "BIM 4D",
            "Visor/selección y cantidades reales; vínculo persistente IFC-actividad y simulación 4D no demostrados.",
            "Capability transversal que consume modelo/versiones y activity references.",
            "O2 / O3",
            "frontend/src/components/BimIfcModelViewer.tsx:1",
            "No segundo cronograma ni recálculo de CPM.",
        ),
        (
            "P1",
            "Ingeniería / QA / HSE / Field",
            "Primitivas AWP/documentales no prueban suite de ejecución ni QA/QC/HSE.",
            "Límites por fuente, evidencia mínima, restricciones vigentes y release según proyecto.",
            "O2 / O3",
            "backend/app/domain/models.py:822",
            "No declarar cumplimiento HSE ni habilitación automática de workfront.",
        ),
        (
            "P2",
            "Claims y closeout",
            "MIP3.7/expediente y reportes de cierre son parciales.",
            "Forensic sobre snapshots aislados; commissioning/handover/readiness/asset/closeout distintos.",
            "O4",
            "frontend/src/navigation/applicationNavigation.ts:626",
            "No modificar schedule actual desde simulación de claim.",
        ),
        (
            "P1",
            "Deuda / rutas / formatos",
            "Vistas legacy y branches baseline/evidence requieren validar accesibilidad; .xls/.mpp detectados no demuestran parser binario.",
            "Auditoría de uso/paridad/compatibilidad y formatos soportados antes de deprecar o publicitar.",
            "O1–O4",
            "frontend/src/App.tsx:7009",
            "SAFE_TO_REMOVE=0; cero borrados propuestos en este incremento.",
        ),
    ]
    gaps = [
        {
            "id": f"GAP-{i:02d}",
            "severity": p,
            "topic": t,
            "current": c,
            "target": g,
            "wave": w,
            "evidence": e,
            "guard": guard,
        }
        for i, (p, t, c, g, w, e, guard) in enumerate(gap_specs, 1)
    ]
    source_text = PROMPT.read_text(encoding="utf-8-sig")
    acceptance_text = source_text.split("# 62. ARCHITECTURE ACCEPTANCE CRITERIA", 1)[
        1
    ].split("# 63.", 1)[0]
    acceptance = [
        {
            "id": f"AC-{i:02d}",
            "criterion": line.strip().split(" = PASS")[0],
            "status": "PASS_ARCHITECTURE_DEFINED_NOT_RUNTIME_TEST",
        }
        for i, line in enumerate(
            re.findall(r"^.+ = PASS$", acceptance_text, re.MULTILINE), 1
        )
    ]
    assert len(acceptance) == 32
    evidence_map = [
        "H01–H15; master §2",
        "ADR86; D01; GAP01",
        "D01–D25 applicability; master §8",
        "ADR87; D19; master §6",
        "D02; ADR90",
        "D03; ADR89",
        "ADR88; p6_manual_schedule_contract",
        "D04; baseline_and_budget_contract",
        "D06; ADR91",
        "D07; ADR93",
        "D08; ADR92",
        "D09/D10; master §7",
        "D11/D12; ADR94",
        "D13",
        "D16; optional AWP",
        "D17/D18",
        "D20",
        "D21–D25",
        "25-domain ADMIN/USER matrix",
        "DO01–DO26",
        "IN01–IN26",
        "BE15/FE25/PH16 evidence units",
        "GAP01–GAP18",
        "28 legacy evidence units; SAFE_TO_REMOVE0",
        "O1–O4",
        "25-node acyclic DAG + O1A/B/C",
        "O1A prerequisite then O1B/C",
        "Single owner matrices; no product edits",
        "ADR88",
        "ADR88",
        "Product SHA baseline/final audit",
        "Product SHA baseline/final audit",
    ]
    for criterion, evidence in zip(acceptance, evidence_map):
        criterion["evidence"] = evidence.replace("GAP01", "GAP-01").replace(
            "GAP18", "GAP-18"
        )
    # ADR files follow the existing global numeric convention; all are proposed.
    for adr in contracts["adrs"]:
        number = int(adr["id"].split()[-1])
        slug = re.sub(r"[^a-z0-9]+", "-", adr["title"].lower()).strip("-")
        path = ROOT / "docs" / f"{number}-adr-operational-{slug}.md"
        content = (
            f"# {adr['id']}: {adr['title']}\n\nStatus: PROPOSED_DESIGN\n\nRequirement alias: {adr['requirement_alias']}\n\nDate: 2026-10-19\n\n## Context\n\n{adr['rationale']}\n\n## Proposed decision\n\n{adr['decision']}\n\n## Consequences and implementation boundary\n\n{adr['implications']}\n\nThis increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.\n\n## Evidence inspected (not tests executed)\n\n"
            + "\n".join(f"- `{ref}`" for ref in adr["evidence"])
            + "\n"
        )
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refuse to overwrite a different ADR: {path}")
        path.write_text(content, encoding="utf-8")
        adr["file"] = path.relative_to(ROOT).as_posix()

    sheets = []
    sheets.append(
        sheet(
            "01_Domain_Map",
            "Mapa de dominios · autoridad y límites propuestos",
            [
                "ID",
                "Capacidad",
                "Clasificación",
                "Propósito",
                "Objetos",
                "Autoridad fuente",
                "Entradas",
                "Salidas",
                "Upstream",
                "Downstream",
                "Handoff",
                "Relación P6",
                "Estado actual",
                "Acción futura",
                "Ola",
                "Complejidad",
                "Justificación",
                "Evidencia",
            ],
            [
                [
                    d["id"],
                    d["name"],
                    d["classification"],
                    d["purpose"],
                    cell(d["objects"]),
                    d["source_authority"],
                    cell(d["inputs"]),
                    cell(d["outputs"]),
                    cell(d["upstream_ids"]),
                    cell(d["downstream_ids"]),
                    d["handoff"],
                    d["p6_relationship"],
                    d["current_status"],
                    d["planned_action"],
                    d["wave"],
                    d["complexity"],
                    d["rationale"],
                    cell(d["source_refs"]),
                ]
                for d in domains
            ],
        )
    )
    process_rows = [
        [
            p["id"],
            "PROCESS",
            p["name"],
            cell(p["domain_ids"]),
            p["description"],
            p["sequence_note"],
        ]
        for p in data["process_map"]
    ]
    process_rows += [
        [
            p["id"],
            "CHECKPOINT",
            p["name"],
            cell(p["domain_ids"]),
            "Entrada: " + cell(p["entry"]) + "\nSalida: " + cell(p["exit"]),
            "No es Investment Gate. Bloquea: " + cell(p["blocked_when"]),
        ]
        for p in data["checkpoints"]
    ]
    sheets.append(
        sheet(
            "02_Process_Map",
            "Flujo conceptual y checkpoints operacionales",
            [
                "ID",
                "Tipo",
                "Paso / checkpoint",
                "Dominios",
                "Descripción / criterios",
                "Límite",
            ],
            process_rows,
        )
    )
    sheets.append(
        sheet(
            "03_Admin_User_Matrix",
            "ADMIN configura/publica · USER ejecuta · consultas compartidas",
            [
                "ID",
                "Capacidad",
                "ADMIN MODE",
                "USER MODE",
                "Compartido lectura",
                "Regla de SoD",
            ],
            [
                [
                    d["id"],
                    d["name"],
                    cell(d["admin_config"]),
                    cell(d["user_operations"]),
                    cell(d["shared_read_only"]),
                    "RBAC tenant/Workspace; preparar no autoriza autoaprobar baseline/progress/change/forecast/award/claim/closeout material.",
                ]
                for d in domains
            ],
        )
    )
    sheets.append(
        sheet(
            "04_Owner_Contractor_Matrix",
            "Aplicabilidad propuesta por modelo de gobierno",
            [
                "ID",
                "Capacidad",
                "CAPITAL_OWNER",
                "CONTRACTOR_DELIVERY",
                "DIRECT_INTERNAL",
                "Condición / tailoring",
            ],
            [
                [
                    d["id"],
                    d["name"],
                    d["applicability"]["CAPITAL_OWNER"],
                    d["applicability"]["CONTRACTOR_DELIVERY"],
                    d["applicability"]["DIRECT_INTERNAL"],
                    d["applicability_note"],
                ]
                for d in domains
            ],
        )
    )
    sheets.append(
        sheet(
            "05_Data_Ownership",
            "Propiedad única por objeto/faceta · sin escrituras ajenas",
            [
                "ID",
                "Objeto / faceta",
                "Dominio fuente",
                "Propietario",
                "Límite actual",
                "Escritura externa",
                "Consumidores snapshot",
                "Regla de comando",
            ],
            [
                [
                    r["id"],
                    r["data_object"],
                    r["source_domain"],
                    r["owner"],
                    r["current_boundaries"],
                    "NO",
                    cell(r["snapshot_consumers"]),
                    r["owner_command_rule"],
                ]
                for r in contracts["ownership_minimum"]
            ],
        )
    )
    sheets.append(
        sheet(
            "06_Integration_Matrix",
            "Integraciones conceptuales · referencias, snapshots y comandos",
            [
                "ID",
                "Fuente",
                "Destino",
                "Datos / evento",
                "Dirección",
                "Modalidad",
                "Autoridad",
                "Prerrequisitos",
                "Escritura tabla ajena",
                "Estado",
            ],
            [
                [
                    r["id"],
                    r["source_domain"],
                    r["target_domain"],
                    r["data_event"],
                    r["direction"],
                    r["reference_snapshot_command"],
                    r["authority"],
                    r["contract_prerequisites"],
                    "NO",
                    r["status"],
                ]
                for r in contracts["integration_matrix"]
            ],
        )
    )
    sheets.append(
        sheet(
            "07_Current_Capabilities",
            "Inventario por evidencia · filas BE/FE/PH no equivalen a funciones únicas",
            [
                "ID evidencia",
                "Capa",
                "Área",
                "Clasificación",
                "Estado / vistas",
                "Observación",
                "Limitaciones",
                "Reutilización / autoridad",
                "Fuente path:line",
                "Tests definidos",
                "Verificación",
            ],
            capabilities,
        )
    )
    sheets.append(
        sheet(
            "08_Gap_Analysis",
            "Brechas verificadas y requisitos futuros · sin corrección de producto aquí",
            [
                "ID",
                "Severidad de diseño",
                "Área",
                "Estado observado",
                "Objetivo",
                "Ola",
                "Evidencia",
                "Guardrail",
            ],
            [
                [
                    r["id"],
                    r["severity"],
                    r["topic"],
                    r["current"],
                    r["target"],
                    r["wave"],
                    r["evidence"],
                    r["guard"],
                ]
                for r in gaps
            ],
        )
    )
    sheets.append(
        sheet(
            "09_Wave_Prioritization",
            "Priorización arquitectónica propuesta · dependencias prevalecen",
            [],
            [],
        )
    )
    deps = data["implementation_dependency_graph"]
    sheets.append(
        sheet(
            "10_Dependency_Map",
            "DAG de implementación · distinto de los ciclos de operación",
            [
                "ID",
                "Capacidad",
                "Ola",
                "Prerrequisitos",
                "Orden topológico",
                "Alcance mínimo / excepción",
            ],
            [
                [
                    d["id"],
                    d["name"],
                    d["wave"],
                    cell(deps["prerequisites"][d["id"]]) or "Ninguno: raíz canónica",
                    deps["topological_order"].index(d["id"]) + 1,
                    deps["optional_domain_rule"] + " " + deps["phasing_note"],
                ]
                for d in domains
            ],
        )
    )
    sheets.append(
        sheet(
            "11_Legacy_Candidates",
            "Candidatos legacy · ningún borrado autorizado",
            [
                "ID",
                "Componente",
                "Decisión",
                "Razón / estado",
                "Evidencia",
                "Acción ejecutada",
                "Condición futura",
            ],
            legacy,
        )
    )
    decision_rows = [
        [
            a["id"],
            a["requirement_alias"],
            a["title"],
            a["status"],
            a["decision"],
            a["rationale"],
            a["implications"],
            cell(a["evidence"]),
            a["file"],
        ]
        for a in contracts["adrs"]
    ]
    decision_rows += [
        [
            r["id"],
            "PROCUREMENT BOUNDARY",
            r["name"],
            "PROPOSED_DESIGN",
            r["procurement_boundary"],
            r["current_state"],
            r["future_owner"],
            cell(r["evidence"]),
            "No nueva autoridad ni borrado",
        ]
        for r in procurement["capabilities"]
    ]
    sheets.append(
        sheet(
            "12_Decisions",
            "ADR86–97 y resolución conceptual de duplicidades",
            [
                "ID",
                "Alias / tipo",
                "Decisión",
                "Estado",
                "Definición",
                "Razón",
                "Consecuencias",
                "Evidencia",
                "Registro",
            ],
            decision_rows,
        )
    )
    full = {
        "schema_version": 1,
        "cutoff_local": "2026-10-19 America/Bogota",
        "status": "PROPOSED_DESIGN_ARCHITECTURE_ONLY",
        "strategic_state_preserved": data["strategic_state_preserved"],
        "domains": domains,
        "process_map": data["process_map"],
        "checkpoints": data["checkpoints"],
        "dependency_graph": deps,
        "minimum_core": data["minimum_viable_operational_core"],
        "contracts": contracts,
        "gaps": gaps,
        "acceptance": acceptance,
        "prioritization": scoring,
        "workbook_sheets": sheets,
        "inventory_counts": {
            "backend": 15,
            "frontend": 25,
            "procurement_handoff": 16,
            "note": "56 evidence units at different granularity, not 56 independent functions",
        },
        "legacy_count": len(legacy),
        "safe_to_remove_count": 0,
    }
    (DESIGN / "architecture-data.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (AUDIT / "architecture-acceptance.json").write_text(
        json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "domains": len(domains),
                "sheets": len(sheets),
                "inventory_evidence_units": len(capabilities),
                "gaps": len(gaps),
                "legacy": len(legacy),
                "acceptance": len(acceptance),
                "adrs": len(contracts["adrs"]),
            }
        )
    )


if __name__ == "__main__":
    main()
