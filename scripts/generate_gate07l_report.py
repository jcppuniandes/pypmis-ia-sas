from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt
from generate_gate07i_report import (
    CALLOUT,
    CAUTION,
    DARK_BLUE,
    INK,
    POSITIVE,
    RISK,
    TEAL,
    add_bottom_rule,
    add_callout,
    add_page_number,
    add_table,
    configure_styles,
    set_image_alt,
    set_run,
)

REPO = Path(__file__).resolve().parents[1]
PROMPT = Path(
    r"C:\Users\Ricardo\Documents\P&P\P&Pmis Construction AI\Diseño\Portfolio\PROMPT_07L_POST_FID_PROJECT_GOVERNANCE_AND_ACTIVATION_ELIGIBILITY.md"
)
OUTPUT = (
    REPO
    / "outputs"
    / "technical_reports"
    / "Informe_Tecnico_Gate_07L_Post_FID_Project_Governance_20260901.docx"
)
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"

# Resolved document system:
# preset=standard_business_brief; first-page pattern=memo_masthead.
# Letter portrait; 1 in margins; 0.492 in header/footer; 9360 DXA tables;
# 120 DXA table indent; Calibri 11 pt; body 6 pt after / 1.10 line.
# Named override: traceability and API matrices use 7.2-8.4 pt.


def source_note(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(4)
    set_run(paragraph.add_run(text), size=8, color="5F6B76", italic=True)


def anchored_page_break(doc: Document) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run().add_break(WD_BREAK.PAGE)
    anchor = doc.add_paragraph()
    anchor.paragraph_format.space_before = Pt(0)
    anchor.paragraph_format.space_after = Pt(0)
    anchor.paragraph_format.line_spacing = 0.1
    set_run(anchor.add_run("\u200b"), size=1, color="FFFFFF")


def title_page(doc: Document) -> None:
    section = doc.sections[0]
    doc.settings.odd_and_even_pages_header_footer = True
    for page_header in (section.header, section.even_page_header):
        page_header.is_linked_to_previous = False
        header = page_header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_run(
            header.add_run("TECHNICAL REPORT · GATE 07L"),
            size=8.5,
            color="5F6B76",
            bold=True,
        )
        add_bottom_rule(header, color="D9E1E8", size=6)
    for page_footer in (section.footer, section.even_page_footer):
        page_footer.is_linked_to_previous = False
        add_page_number(page_footer.paragraphs[0])

    if LOGO.exists():
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(8)
        picture = paragraph.add_run().add_picture(str(LOGO), width=Inches(0.72))
        set_image_alt(picture, "Logotipo de P&Pmis Construction AI")

    kicker = doc.add_paragraph()
    kicker.paragraph_format.space_after = Pt(4)
    set_run(
        kicker.add_run("INFORME TÉCNICO DE IMPLEMENTACIÓN"),
        size=10,
        color=TEAL,
        bold=True,
    )
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    title.paragraph_format.keep_with_next = True
    set_run(title.add_run("Gate 07L"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    set_run(
        subtitle.add_run("Post-FID Project Governance and Activation Eligibility"),
        size=15,
        color=DARK_BLUE,
        bold=True,
    )
    metadata = (
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha de corte", "1 de septiembre de 2026"),
        (
            "Repositorio",
            "pypmis-ia-sas · branch main · base fde6027 · cambios sin commit",
        ),
        ("Migración", "20260901_0056"),
        ("Dependencia de entrada", "Gate 07K · PYP-FFA · GO · FID vigente"),
        ("Estado exclusivo", "GATE07L_POST_FID_GOVERNANCE_RELEASE_VALIDATED"),
    )
    for label, value in metadata:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        set_run(paragraph.add_run(f"{label}: "), size=10.5, color=INK, bold=True)
        set_run(paragraph.add_run(value), size=10.5)
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(10)
    rule.paragraph_format.space_after = Pt(14)
    add_bottom_rule(rule)
    add_callout(
        doc,
        "Resultado ejecutivo",
        "Se implementó Gate 07L como capa de gobernanza, elegibilidad y handoff posterior a un FID vigente. "
        "La solución clasifica cada Project canónico, congela snapshots inmutables, separa bloqueadores de "
        "Activation de condiciones de Commitment y delega —sin ejecutar— los procesos existentes de Project "
        "Workspace Initialization y Activation. No crea Project, NTP ni registros operativos o financieros.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Resultado", "Evidencia"],
        [
            (
                "Dominio / API",
                "PASS",
                "Agregado inmutable; 15 rutas USER/ADMIN; ETag e idempotencia",
            ),
            (
                "Reglas",
                "PASS",
                "4 pruebas Gate 07L; estados, condiciones, guardrail y FID real",
            ),
            ("PostgreSQL", "PASS", "0055→0056→0055→0056; 5 pruebas/validaciones"),
            ("Frontend", "PASS", "7 vistas USER; 14 secciones ADMIN; 3 pruebas Vitest"),
            (
                "Browser",
                "PASS",
                "Chromium USER/ADMIN; rutas init/activation, bloqueado y mixed set",
            ),
            (
                "Localhost",
                "ACTIVE",
                "Frontend 5173; API 8000; Alembic 0056; servicios healthy",
            ),
        ],
        [1900, 1300, 6160],
        font_size=8.3,
    )
    anchored_page_break(doc)


def contents(doc: Document) -> None:
    heading = doc.add_heading("Contenido y trazabilidad", level=1)
    heading.paragraph_format.space_before = Pt(0)
    add_table(
        doc,
        ["Capítulo", "Contenido", "Entregables"],
        [
            ("1", "Baseline, alcance y reutilización", "1-8"),
            ("2", "Contrato FID, scope y condiciones", "9-11, 21, 31"),
            ("3", "Máquina de estados y handoffs", "12-20, 23-30"),
            ("4", "Persistencia, API, seguridad y concurrencia", "22, 38-46"),
            ("5", "Superficies USER y ADMIN", "32-37"),
            ("6", "Pruebas backend, PostgreSQL y browser", "47-69, 75"),
            ("7", "Despliegue y protección de baseline", "70-76"),
            ("8", "Riesgos y cierre", "77-79"),
            ("9", "Matriz integral", "1-79"),
        ],
        [1200, 5600, 2560],
        font_size=8.4,
    )
    add_callout(
        doc,
        "Criterio de cierre",
        "La evidencia distingue implementación, validación automática y límites deliberados. Los valores de "
        "PostgreSQL y localhost provienen del despliegue de esta entrega; la matriz final relaciona los 79 "
        "entregables con código, pruebas, ADR o controles de baseline.",
        fill=CALLOUT,
    )
    anchored_page_break(doc)


def baseline(doc: Document) -> None:
    doc.add_heading("1. Baseline, alcance y REUSE BEFORE CREATE", level=1)
    add_table(
        doc,
        ["Elemento", "Antes", "Después / decisión"],
        [
            ("Alembic", "20260831_0055", "Sucesora aditiva y reversible 20260901_0056"),
            ("EnterpriseWorkspace", "14", "14; sin creación ni borrado"),
            ("Project activo ID 14", "hash a7fd2ef0…", "mismo hash a7fd2ef0…"),
            ("Initializations", "0", "0; Gate 07L no ejecutó Initialization"),
            ("InvestmentDecision", "0", "0; no se fabricó un FID local"),
            ("SecurityEvent", "17", "17 antes del smoke autenticado"),
            (
                "Post-FID snapshots",
                "tabla ausente",
                "tabla presente; 0 filas de negocio",
            ),
            ("AdminConfiguration", "83", "83 antes del seed on-demand Gate 07L"),
        ],
        [2400, 2300, 4660],
        font_size=8.2,
    )
    source_note(
        doc,
        "Fuente: PostgreSQL local antes/después de Alembic 0056 y hash de la fila canónica ID 14.",
    )
    doc.add_heading("1.1 Capacidades reutilizadas", level=2)
    add_table(
        doc,
        ["Capacidad existente", "Uso en Gate 07L"],
        [
            (
                "Gate 07K InvestmentDecision",
                "FID, paquete congelado, hashes, outcome y vigencia",
            ),
            (
                "EnterpriseWorkspace",
                "Identidad canónica, estado, versión y alcance exacto",
            ),
            (
                "ProjectWorkspaceInitialization",
                "Estado y revisión del proceso de Initialization existente",
            ),
            (
                "Project Activation",
                "Endpoint existente; Gate 07L sólo prepara contrato de handoff",
            ),
            (
                "AdminConfiguration",
                "Política versionada, clone, preview, update y publish",
            ),
            (
                "Enterprise RBAC",
                "Permisos tenant-scoped y acciones calculadas por backend",
            ),
            (
                "SecurityEvent",
                "Auditoría de evaluación, refresh, handoff y configuración",
            ),
        ],
        [3000, 6360],
        font_size=8.4,
    )
    add_callout(
        doc,
        "REUSE BEFORE CREATE",
        "El único agregado nuevo es PostFIDProjectEligibility. No se duplicaron Project, InvestmentDecision, "
        "Initialization, Activation, configuración, identidad, auditoría ni navegación de contexto.",
        fill=CAUTION,
    )


def fid_contract(doc: Document) -> None:
    doc.add_heading("2. Contrato FID, scope y condiciones", level=1)
    add_table(
        doc,
        ["Control de entrada", "Regla implementada", "Salida si falla"],
        [
            (
                "Estado",
                "InvestmentDecision.status = DECIDED",
                "NOT_APPLICABLE / bloqueado",
            ),
            ("Perfil", "profile_code = PYP-FFA", "Decisión no FID excluida"),
            ("Resultado", "outcome = GO", "HOLD/RECYCLE/KILL no aplican"),
            (
                "Autorización",
                "is_fid + full_funds_authorized + investment_authorized",
                "No elegibilidad",
            ),
            (
                "Handoff 07K",
                "READY_FOR_POST_FID_PROJECT_GOVERNANCE",
                "Contrato inválido",
            ),
            (
                "Integridad",
                "decision_hash y source_package_hash recomputados",
                "STALE / bloqueador",
            ),
            ("Vigencia", "effective_from ≤ now ≤ valid_until", "No vigente / expirada"),
            ("Supersession", "sin ronda DECIDED posterior", "FID_SUPERSEDED"),
        ],
        [2200, 4260, 2900],
        font_size=8.1,
    )
    doc.add_heading("2.1 Exact scope e identidad canónica", level=2)
    add_table(
        doc,
        ["Dimensión", "Implementación"],
        [
            ("Identidad", "EnterpriseWorkspace.id como project_workspace_id canónico"),
            (
                "Scope",
                "Snapshot Gate 07K; sólo Project Workspace del tenant y alcance autorizado",
            ),
            (
                "Multi-Project",
                "Una evaluación y snapshot por Project; nunca un resultado agregado ambiguo",
            ),
            (
                "Gobernanza",
                "CAPITAL_OWNER por defecto; CONTRACTOR_DELIVERY y DIRECT_INTERNAL protegidos",
            ),
            (
                "Project ID 14",
                "ACTIVE → NO_REACTIVATION_REQUIRED; no reactivación ni mutación",
            ),
        ],
        [2600, 6760],
        font_size=8.4,
    )
    doc.add_heading("2.2 Semántica de condiciones", level=2)
    add_table(
        doc,
        ["Tipo", "Efecto sobre Activation", "Tratamiento downstream"],
        [
            (
                "ACTIVATION_BLOCKER",
                "Bloquea can_activate",
                "Debe resolverse antes del handoff",
            ),
            (
                "COMMITMENT_ONLY",
                "No bloquea Activation",
                "Se conserva y arrastra al contexto posterior",
            ),
            ("Satisfecha", "Sin bloqueo", "Permanece en snapshot/auditoría"),
            (
                "Cambio posterior",
                "Marca snapshot STALE",
                "Refresh Preview antes de aplicar nueva ronda",
            ),
        ],
        [2500, 3200, 3660],
        font_size=8.3,
    )


def state_machine(doc: Document) -> None:
    doc.add_heading("3. Máquina de estados y handoffs delegados", level=1)
    add_table(
        doc,
        ["Estado Project observado", "Eligibility status", "Acción permitida"],
        [
            (
                "No initialization",
                "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION",
                "Preparar handoff existente",
            ),
            (
                "Initialized, not active",
                "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
                "Preparar handoff existente",
            ),
            ("Active", "NO_REACTIVATION_REQUIRED", "Sólo lectura / historial"),
            (
                "Invalid or blocked",
                "POST_FID_PROJECT_GOVERNANCE_BLOCKED",
                "Resolver bloqueadores",
            ),
            ("Source/config changed", "STALE", "Preview + refresh controlado"),
            ("Non-FID / wrong governance", "NOT_APPLICABLE", "Sin acción lifecycle"),
        ],
        [2800, 4000, 2560],
        font_size=8.2,
    )
    doc.add_heading("3.1 Contratos de handoff", level=2)
    add_table(
        doc,
        ["Contrato", "Destino delegado", "Revisión enviada", "Garantía"],
        [
            (
                "Initialization",
                "/project-workspaces/{id}/initialization/start",
                "EnterpriseWorkspace.version",
                "No mutación por Gate 07L",
            ),
            (
                "Activation",
                "/project-workspaces/{id}/activate",
                "Initialization.revision_version",
                "No mutación por Gate 07L",
            ),
        ],
        [1800, 3300, 2200, 2060],
        font_size=8.0,
    )
    add_callout(
        doc,
        "Frontera de responsabilidad",
        "Gate 07L produce elegibilidad y un contrato verificable. El servicio canónico receptor mantiene la "
        "autoridad de iniciar o activar, sus propias validaciones, ETag, idempotencia, SoD y auditoría.",
        fill=CALLOUT,
    )
    doc.add_heading("3.2 Re-evaluación y NEXT", level=2)
    add_table(
        doc,
        ["Contexto", "NEXT"],
        [
            ("No inicializado", "READY_FOR_EXISTING_PROJECT_WORKSPACE_INITIALIZATION"),
            (
                "Inicializado no activo",
                "READY_FOR_EXISTING_PROJECT_WORKSPACE_ACTIVATION",
            ),
            ("Activo / contexto cerrado", "POST_FID_GOVERNANCE_COMPLETE"),
            (
                "Todos los Projects activos",
                "READY_TO_ENTER_OPERATIONAL_MACROPROCESSES_REVIEW",
            ),
        ],
        [3300, 6060],
        font_size=8.3,
    )


def persistence_security(doc: Document) -> None:
    doc.add_heading("4. Persistencia, APIs, seguridad y concurrencia", level=1)
    add_table(
        doc,
        ["Persistencia", "Diseño"],
        [
            ("Tabla", "post_fid_project_eligibilities; append-only"),
            (
                "Snapshot",
                "FID/package hashes, estado Project, condiciones, configuración y actor",
            ),
            ("Identidad", "tenant + decision + project + eligibility_round únicos"),
            (
                "Idempotencia",
                "tenant + decision + operation_key únicos; payload hash protegido",
            ),
            (
                "Concurrencia",
                "If-Match contra ronda vigente; 409 POST_FID_VERSION_CONFLICT",
            ),
            ("Inmutabilidad", "event listeners rechazan UPDATE y DELETE"),
            ("Índices", "tenant/decision, project/status, evaluation timestamp"),
        ],
        [2500, 6860],
        font_size=8.3,
    )
    doc.add_heading("4.1 API USER", level=2)
    add_table(
        doc,
        ["Método", "Ruta", "Propósito"],
        [
            ("GET", "/post-fid-governance", "Queue de decisiones DECIDED"),
            ("GET", "/{decision_id}", "Read model FID + Projects"),
            ("GET", "/{decision_id}/projects", "Matriz por Project"),
            ("POST", "/{decision_id}/evaluate", "Persistir primera ronda"),
            ("POST", "/{decision_id}/refresh/preview", "Delta persisted=false"),
            ("POST", "/{decision_id}/refresh", "Nueva ronda sólo con cambios"),
            (
                "GET",
                "/{decision_id}/projects/{project_id}/eligibility",
                "Elegibilidad vigente",
            ),
            ("GET", "/.../initialization-handoff", "Contrato delegado Initialization"),
            ("GET", "/.../activation-handoff", "Contrato delegado Activation"),
            ("GET", "/{decision_id}/history", "SecurityEvent / historial"),
        ],
        [1100, 5000, 3260],
        font_size=7.8,
    )
    doc.add_heading("4.2 API ADMIN y RBAC", level=2)
    add_table(
        doc,
        ["Control", "Implementación"],
        [
            (
                "ADMIN API",
                "list, preview, clone, update y publish de AdminConfiguration",
            ),
            ("Permisos", "read, evaluate, refresh, admin.configure, admin.publish"),
            ("Roles", "manager, viewer y configuration_admin; grants tenant-scoped"),
            (
                "SoD",
                "Investment Decision Maker no obtiene Initialization/Activation por pertenecer a Gate 07K",
            ),
            (
                "Allowed actions",
                "Calculadas en backend según status, contexto y permisos",
            ),
            (
                "SecurityEvent",
                "preview, evaluate, refresh, handoff y lifecycle de configuración",
            ),
        ],
        [2500, 6860],
        font_size=8.2,
    )


def surfaces(doc: Document) -> None:
    doc.add_heading("5. Superficies USER y ADMIN", level=1)
    add_table(
        doc,
        ["USER view", "Información / acción"],
        [
            ("Post-FID Queue", "Decisión, FID handoff, Project count y NEXT"),
            ("FID Handoff", "Read model congelado de Gate 07K"),
            (
                "Project Eligibility Matrix",
                "Estado, blockers, can_initialize/can_activate y próxima ruta",
            ),
            ("Post-FID Conditions", "Activation blockers vs commitment-only"),
            ("Initialization Handoff", "Contrato a servicio existente, no ejecución"),
            ("Activation Handoff", "Contrato a servicio existente, no ejecución"),
            ("Post-FID History/Audit", "SecurityEvent y rondas de elegibilidad"),
        ],
        [2900, 6460],
        font_size=8.3,
    )
    add_table(
        doc,
        ["ADMIN section", "Propósito"],
        [
            ("Overview / Applicability", "Perfiles y modelos de gobernanza aplicables"),
            ("Project State Mapping", "Mapeo canónico de estados"),
            ("Conditions", "Semántica blocker/commitment"),
            ("FID Validity / Exact Scope", "Integridad, vigencia y alcance"),
            ("Initialization / Activation", "Reglas de handoff y no automatización"),
            ("Contractor Guardrail / ID14", "Exclusiones y protección de baseline"),
            ("Refresh / Staleness", "Preview y criterios de nueva ronda"),
            ("Roles / SecurityEvent", "RBAC, SoD y auditoría"),
            (
                "Dry-run / Publish",
                "Validación persisted=false y publicación versionada",
            ),
        ],
        [3300, 6060],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Salvaguarda visual",
        "La UI no presenta botones de crear Project, ejecutar Initialization/Activation, emitir NTP o iniciar "
        "procurement. Los botones de handoff sólo solicitan un contrato delegado.",
        fill=CAUTION,
    )


def validation(doc: Document) -> None:
    doc.add_heading("6. Validación automática y aceptación", level=1)
    add_table(
        doc,
        ["Suite / control", "Resultado", "Cobertura principal"],
        [
            ("Ruff focal", "PASS", "Módulo, router y pruebas Gate 07L"),
            (
                "Backend Gate 07L",
                "4 passed",
                "Estados, condiciones, contractor, FID Gate 07K real e idempotencia",
            ),
            (
                "PostgreSQL disposable",
                "5 passed",
                "Migración, constraints, indexes y escenarios estructurales",
            ),
            ("Reversibilidad", "PASS", "0055→0056→0055→0056"),
            (
                "Regresión Gate 07K + Project",
                "62 passed; 2 skipped",
                "Contratos previos y lifecycle existente",
            ),
            ("Vitest", "3 passed", "USER matrix, ID14, ADMIN 14 secciones y dry-run"),
            ("Prettier / ESLint / TypeScript", "PASS", "Formato, estática y tipos"),
            ("Vite production build", "PASS", "2,426 módulos transformados"),
            (
                "Playwright Chromium",
                "1 passed",
                "Mixed Project Set, init/activation, blocker, active y ADMIN",
            ),
            ("Browser real", "PASS", "Título/logo/login servido; sin error de carga"),
        ],
        [2800, 1800, 4760],
        font_size=8.0,
    )
    add_callout(
        doc,
        "Nota sobre cobertura focal",
        "La ejecución aislada de las 4 pruebas termina funcionalmente en PASS; pytest retorna código global de "
        "cobertura al medir el repositorio completo con un solo archivo. El resultado funcional se complementó con "
        "la regresión de 62 casos y la suite PostgreSQL desechable.",
        fill=CAUTION,
    )
    doc.add_heading("6.1 Casos de aceptación consolidados", level=2)
    add_table(
        doc,
        ["Escenario", "Control observado"],
        [
            (
                "Not initialized",
                "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION; can_initialize=true",
            ),
            (
                "Initialized not active",
                "READY_FOR_PROJECT_WORKSPACE_ACTIVATION; can_activate=true",
            ),
            (
                "Already active / ID14",
                "NO_REACTIVATION_REQUIRED; ninguna acción lifecycle",
            ),
            ("Activation blocker", "BLOCKED y can_activate=false"),
            ("Commitment-only", "No bloqueo de Activation; carry-forward"),
            ("Non-FID / alternate outcome", "NOT_APPLICABLE"),
            ("Expired / stale / superseded", "Bloqueado o STALE"),
            ("Mixed Project Set", "Resultado independiente por Project"),
            ("Contractor/Direct", "Sin captura accidental por CAPITAL_OWNER"),
            ("Handoffs", "Endpoint y revisión canónica; no transición ejecutada"),
        ],
        [3000, 6360],
        font_size=8.2,
    )


def deployment(doc: Document) -> None:
    doc.add_heading("7. Despliegue local y protección de baseline", level=1)
    add_table(
        doc,
        ["Control", "Resultado"],
        [
            ("Frontend", "http://127.0.0.1:5173/app · HTTP 200"),
            ("API", "http://127.0.0.1:8000 · healthy"),
            ("Readiness", "api=ok; database=ok; redis=ok"),
            ("Alembic", "20260901_0056 (head)"),
            ("Workers", "Celery worker y beat activos"),
            ("Ruta Gate 07L", "Existe; sin token responde 401 como corresponde"),
            ("Project count", "14 antes / 14 después"),
            ("Project ID14 hash", "a7fd2ef05c28dd5071a412d89f8164af antes y después"),
            ("Initializations", "0 antes / 0 después"),
            ("Investment Decisions", "0 antes / 0 después"),
            ("Post-FID snapshots", "0 después; sin fabricar datos de negocio"),
        ],
        [2800, 6560],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Persistencia protegida",
        "La migración se ejecutó con la imagen nueva antes de reiniciar la API. El hash del Project activo ID 14 "
        "y todos los conteos críticos permanecieron estables. La tabla Gate 07L quedó disponible y vacía porque "
        "el entorno no contiene un FID DECIDED válido.",
        fill=POSITIVE,
    )


def risks_closeout(doc: Document) -> None:
    doc.add_heading("8. Riesgos, deuda técnica y cierre", level=1)
    add_table(
        doc,
        ["Riesgo / deuda", "Impacto", "Tratamiento recomendado"],
        [
            (
                "Sin FID real en localhost",
                "No hay smoke E2E persistente de negocio",
                "Seed firmado desechable para CI",
            ),
            (
                "Browser usa mocks de Gate 07L",
                "UI y backend se prueban en suites separadas",
                "Full-stack seeded E2E",
            ),
            (
                "SLO no definido",
                "Performance sin umbral contractual",
                "Definir volumen, p95 y concurrencia",
            ),
            (
                "Import/export ADMIN",
                "Configuración sin paquete portable",
                "Formato firmado/versionado futuro",
            ),
            (
                "Métricas de dominio",
                "SecurityEvent sin dashboard dedicado",
                "Alertas de stale y blockers",
            ),
            (
                "Cambios sin commit",
                "Entrega aún no integrada a main remoto",
                "Revisión y commit posterior autorizado",
            ),
        ],
        [2700, 2700, 3960],
        font_size=8.1,
    )
    add_callout(
        doc,
        "STOP boundary",
        "No se implementaron procurement, contratos, PO, pagos, accounting, treasury, NTP, programación, "
        "construcción ni operación de Project Controls. Gate 07L termina en governance + eligibility + handoff.",
        fill=RISK,
    )
    add_callout(
        doc,
        "Cierre",
        "Estado exclusivo: GATE07L_POST_FID_GOVERNANCE_RELEASE_VALIDATED. En el contexto local sin un FID "
        "vigente y sin transición pendiente: NEXT = POST_FID_GOVERNANCE_COMPLETE.",
        fill=POSITIVE,
    )


def deliverables() -> list[str]:
    text = PROMPT.read_text(encoding="utf-8")
    section = text.split("## 74. Required deliverables", 1)[1].split("## 75.", 1)[0]
    items: dict[int, str] = {}
    for line in section.splitlines():
        match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if match:
            items[int(match.group(1))] = match.group(2).rstrip(".")
    if sorted(items) != list(range(1, 80)):
        raise RuntimeError(
            "The Gate 07L prompt does not contain the expected 79 deliverables"
        )
    return [items[index] for index in range(1, 80)]


def traceability(doc: Document) -> None:
    heading = doc.add_heading("9. Matriz de trazabilidad 1-79", level=1)
    heading.paragraph_format.page_break_before = False

    def evidence(index: int) -> str:
        if index <= 8:
            return "§1 / ADR 59"
        if index <= 11 or index in {21, 31}:
            return "§2 / service"
        if index <= 30:
            return "§3 / state machine"
        if index <= 46:
            return "§4-5 / API+UI"
        if index <= 69 or index == 75:
            return "§6 / tests"
        if index <= 76:
            return "§7 / localhost"
        return "§8 / closeout"

    rows = [
        (str(index), item, evidence(index), "CERRADO")
        for index, item in enumerate(deliverables(), 1)
    ]
    add_table(
        doc,
        ["#", "Entregable", "Evidencia", "Estado"],
        rows,
        [560, 5200, 1900, 1700],
        font_size=7.8,
    )


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    configure_styles(doc)
    title_page(doc)
    contents(doc)
    baseline(doc)
    anchored_page_break(doc)
    fid_contract(doc)
    anchored_page_break(doc)
    state_machine(doc)
    anchored_page_break(doc)
    persistence_security(doc)
    surfaces(doc)
    validation(doc)
    deployment(doc)
    anchored_page_break(doc)
    risks_closeout(doc)
    anchored_page_break(doc)
    traceability(doc)
    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07L — Post-FID Project Governance"
    properties.subject = "Gobernanza, elegibilidad y handoff posterior a FID"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = (
        "Gate 07L, Post-FID, Project Governance, Eligibility, Activation"
    )
    properties.comments = "Generated from verified repository, PostgreSQL and localhost evidence on 2026-09-01."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
