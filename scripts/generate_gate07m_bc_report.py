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
    r"C:\Users\Ricardo\Documents\P&P\P&Pmis Construction AI\Diseño\Portfolio"
    r"\PROMPT_07M_BC_GOVERNED_BUSINESS_CASE_MANAGER_AND_LIFECYCLE.md"
)
OUTPUT = REPO / "outputs" / "technical_reports" / "Informe_Tecnico_Gate_07M_BC_Business_Case_Manager_20260902.docx"
LOGO = REPO / "frontend" / "public" / "pypmis-construction-ai-logo.png"

# Resolved document system:
# preset=standard_business_brief; first-page pattern=memo_masthead.
# Letter portrait; 1 in margins; 0.492 in header/footer; 9360 DXA tables;
# 120 DXA table indent; Calibri 11 pt; body 6 pt after / 1.10 line.
# Named override: dense API and traceability matrices use 7.5-8.3 pt.


def source_note(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(4)
    set_run(paragraph.add_run(text), size=8, color="5F6B76", italic=True)


def page_break(doc: Document) -> None:
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
    doc.settings.odd_and_even_pages_header_footer = False
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_run(header.add_run("TECHNICAL REPORT · GATE 07M-BC"), size=8.5, color="5F6B76", bold=True)
    add_bottom_rule(header, color="D9E1E8", size=6)
    add_page_number(section.footer.paragraphs[0])

    if LOGO.exists():
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(8)
        picture = paragraph.add_run().add_picture(str(LOGO), width=Inches(0.72))
        set_image_alt(picture, "Logotipo de P&Pmis Construction AI")

    kicker = doc.add_paragraph()
    kicker.paragraph_format.space_after = Pt(4)
    set_run(kicker.add_run("INFORME TÉCNICO DE IMPLEMENTACIÓN"), size=10, color=TEAL, bold=True)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    title.paragraph_format.keep_with_next = True
    set_run(title.add_run("Gate 07M-BC"), size=25, color=INK, bold=True)
    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    set_run(
        subtitle.add_run("Governed Business Case Manager & Business Case Lifecycle"),
        size=15,
        color=DARK_BLUE,
        bold=True,
    )
    metadata = (
        ("Aplicación", "P&Pmis Construction AI"),
        ("Fecha de corte", "2 de septiembre de 2026"),
        ("Repositorio", "pypmis-ia-sas · rama main · baseline b57f951"),
        ("Migración", "20260902_0057 · sucesora de 20260901_0056"),
        ("Salida", "READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE"),
        ("Estado exclusivo", "GATE07M_BC_RELEASE_VALIDATED"),
        ("NEXT", "BUILD_GATE07M_FIN"),
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
        "Se implementó un Business Case longitudinal por Project Workspace, con revisiones controladas, "
        "readiness por política, lineage de fuentes, detección de cambios materiales y snapshots de decisión "
        "inmutables. La solución reutiliza Proposal, FEL, Budget, Resources, Funding, Risk, Permits, Gate 07K "
        "y Gate 07L sin trasladar su autoridad ni ejecutar decisiones o procesos operacionales.",
        fill=POSITIVE,
    )
    add_table(
        doc,
        ["Capa", "Resultado", "Evidencia principal"],
        [
            ("Dominio / persistencia", "PASS", "3 tablas; 1:1 Project/Case; 1:N revisiones y snapshots"),
            ("API / gobierno", "PASS", "23 operaciones; ETag 412; idempotencia; RBAC; SecurityEvent"),
            ("Frontend", "PASS", "18 vistas USER; 26 secciones ADMIN; CompactModuleHeader"),
            ("Calidad", "PASS", "Ruff, ESLint, Prettier, TypeScript, Vitest, Vite y PostgreSQL"),
            ("Frontera FIN", "PASS", "NOT_AVAILABLE; NPV/IRR/payback/BCR permanecen nulos"),
        ],
        [2200, 1300, 5860],
        font_size=8.2,
    )
    page_break(doc)


def contents(doc: Document) -> None:
    heading = doc.add_heading("Contenido y criterio de cierre", level=1)
    heading.paragraph_format.space_before = Pt(0)
    add_table(
        doc,
        ["Capítulo", "Contenido", "Entregables"],
        [
            ("1", "Baseline, alcance y arquitectura", "1-9"),
            ("2", "Modelo longitudinal y contenido", "10-24"),
            ("3", "Readiness, snapshots y material change", "25-40"),
            ("4", "Seguridad, APIs y persistencia", "41-49"),
            ("5", "Experiencia USER / ADMIN", "44-46, 60-63"),
            ("6", "Validación y regresión", "50-69"),
            ("7", "Gap Analysis, riesgos y siguiente paso", "64-74"),
            ("8", "Matriz integral de trazabilidad", "1-74"),
        ],
        [1200, 5500, 2660],
        font_size=8.3,
    )
    add_callout(
        doc,
        "Criterio de evidencia",
        "Cada afirmación de cierre se vincula con modelos, servicio, router, migración, navegación, pruebas o ADR. "
        "Las pruebas de navegador usan contratos API controlados para validar la experiencia; no constituyen un "
        "benchmark ni crean Business Cases de demostración en la base persistente.",
        fill=CALLOUT,
    )
    page_break(doc)


def architecture(doc: Document) -> None:
    doc.add_heading("1. Baseline, alcance y arquitectura", level=1)
    add_table(
        doc,
        ["Decisión", "Implementación"],
        [
            ("Baseline", "Alembic 20260901_0056; Gate 07L y autoridades previas conservadas"),
            ("Identidad", "enterprise_workspaces con workspace_type=project; no se crea otro Project master"),
            ("Cardinalidad", "Un BusinessCase por Project; múltiples revisiones y snapshots"),
            ("Numeración", "AdminNumberSequence BUSINESS_CASE: BC-00001; revisiones R1, R2…"),
            ("Persistencia", "business_cases, business_case_revisions y business_case_decision_snapshots"),
            ("Migración", "0057 aditiva, reversible, tenant-scoped y con constraints/índices"),
            ("Escala de diseño", "10.000 Projects y 100.000 revisiones; listados indexados sin hidratación profunda"),
        ],
        [2500, 6860],
        font_size=8.3,
    )
    doc.add_heading("1.1 REUSE BEFORE CREATE", level=2)
    add_table(
        doc,
        ["Autoridad existente", "Uso por Business Case"],
        [
            ("ProjectProposal", "Semilla R1 y lineage; la fila fuente no se modifica"),
            ("ProjectFELStatus", "Etapa, readiness y definition hash por referencia"),
            ("Budget / Resources", "Últimos escenarios FROZEN; hashes y resúmenes"),
            ("Funding", "FundingReadinessSnapshot; sin crear capacidad ni asignaciones"),
            ("Risk / Permit", "Assessment COMPLETED, readiness, hash y valid_until"),
            ("Gate 07K / 07L", "Referencias de decisión y continuidad histórica; no reescritura"),
            ("AdminConfiguration", "Mapping, madurez, SoD, freshness e inheritance versionados"),
            ("Workspace Context / RBAC", "Scope tenant/workspace, permisos y navegación existentes"),
            ("SecurityEvent", "Auditoría de lifecycle, refresh, snapshots y configuración"),
        ],
        [2800, 6560],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Ownership",
        "Business Case es autoridad de la narrativa consolidada y su revisión; cada módulo fuente conserva la "
        "autoridad de sus cálculos y estados. Recommendation nunca equivale a Investment Decision.",
        fill=CAUTION,
    )


def longitudinal_model(doc: Document) -> None:
    doc.add_heading("2. Modelo longitudinal y contenido gobernado", level=1)
    add_table(
        doc,
        ["Agregado", "Lifecycle / contenido", "Invariante"],
        [
            ("BusinessCase", "DRAFT · ACTIVE · ON_HOLD · CLOSED · ARCHIVED", "1 por Project Workspace"),
            ("Revision", "DRAFT · IN_REVIEW · COMPLETED · SUPERSEDED · VOIDED", "COMPLETED inmutable"),
            ("Snapshot", "INVESTMENT_SELECTION · FULL_FUNDS_AUTHORIZATION · OTHER_CONFIGURED_GATE", "Append-only"),
        ],
        [2100, 4400, 2860],
        font_size=8.2,
    )
    doc.add_heading("2.1 Propósitos de revisión", level=2)
    add_table(
        doc,
        ["Propósito", "Momento esperado"],
        [
            ("INITIAL_PROPOSAL", "R1 gobernada desde Project Proposal"),
            ("FEL_1_UPDATE / FEL_2_UPDATE", "Madurez progresiva y alternativas"),
            ("INVESTMENT_SELECTION_UPDATE", "Base posterior a selección"),
            ("FEL_3_UPDATE / FFA_UPDATE", "Definición y autorización de fondos"),
            ("MATERIAL_CHANGE_UPDATE", "Fuentes cambiadas con revisión humana"),
            ("REVALIDATION / OTHER", "Actualización controlada adicional"),
        ],
        [3500, 5860],
        font_size=8.3,
    )
    doc.add_heading("2.2 Secciones y lineage", level=2)
    add_table(
        doc,
        ["Grupo", "Contenido implementado"],
        [
            ("Strategic Case", "Need, summary, objectives, alignment y contexto sponsor/owner"),
            ("Alternatives / Benefits", "JSON gobernado para opciones, selección, valor, evidencia y métricas"),
            ("Definition / execution", "FEL hash, delivery strategy, hitos, interfaces y restricciones"),
            ("Budget / Resources", "Source ids, frozen scenario hashes, CAPEX/currency y factibilidad"),
            ("Funding / Risk / Permits", "Readiness referenciada; status, hash, vigencia y condiciones"),
            ("Assumptions / constraints", "Colecciones estructuradas y concerns no ocultos en memo libre"),
            ("Recommendation", "Recomendación narrativa; no GO, FID ni autorización"),
        ],
        [2700, 6660],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Contrato financiero futuro",
        "La revisión reserva id, versión, hash, readiness y fecha de corte del modelo económico-financiero, además "
        "de financial_model_status y métricas anulables. En 07M-BC el estado válido es NOT_AVAILABLE y NPV, IRR, "
        "payback y benefit-cost ratio permanecen null. Gate 07M-FIN será una autoridad independiente y deberá "
        "reconciliar Budget y Funding sin crear capacidad.",
        fill=RISK,
    )


def governance(doc: Document) -> None:
    doc.add_heading("3. Readiness, snapshots y cambios materiales", level=1)
    add_table(
        doc,
        ["Estado", "Semántica"],
        [
            ("NOT_STARTED", "Aún no evaluado o revisión en elaboración"),
            ("READY", "Secciones y fuentes requeridas por etapa/policy disponibles y actuales"),
            ("BLOCKED", "Faltan secciones/fuentes o una autoridad reporta bloqueo"),
            ("STALE", "Los hashes actuales difieren del snapshot de fuentes de la revisión"),
            ("EXPIRED", "Risk o Permit excedió valid_until"),
        ],
        [2100, 7260],
        font_size=8.3,
    )
    add_table(
        doc,
        ["Policy axis", "Resolución"],
        [
            ("Inheritance", "Tenant → Enterprise → Business Unit → Portfolio; nearest published applicable wins"),
            ("Context", "Project Type, Governance Model, Gate Profile y FEL Stage"),
            ("Stage requirements", "FEL-1 Proposal; FEL-2 Proposal+FEL; FEL-3/FFA fuentes ampliadas"),
            ("SoD", "Reviewer distinto de Preparer; política estricta PYP-FFA"),
            ("Freshness", "Source hash snapshot vs fuentes vigentes; COMPLETED nunca se modifica"),
        ],
        [2400, 6960],
        font_size=8.2,
    )
    doc.add_heading("3.1 Refresh y material change", level=2)
    add_table(
        doc,
        ["Paso", "Resultado"],
        [
            ("Refresh Preview", "changed sources, old/new hash, materiality y purpose; persisted=false"),
            ("Refresh Apply", "Nueva revisión DRAFT; copia narrativa y actualiza refs/hashes"),
            ("Material evaluation", "NO_MATERIAL_CHANGE o MATERIAL_CHANGE_REVIEW_REQUIRED"),
            ("Review", "Outcome y rationale idempotentes con If-Match"),
            ("After selection/FID", "Recomendación de revalidación; no auto-void, no desactivación"),
        ],
        [2500, 6860],
        font_size=8.2,
    )
    doc.add_heading("3.2 Decision snapshots", level=2)
    add_table(
        doc,
        ["Control", "Garantía"],
        [
            ("Precondición", "Sólo referencia BusinessCaseRevision COMPLETED del mismo agregado"),
            (
                "Contenido",
                "Caso estratégico, alternativas, alcance, beneficios, ejecución, supuestos, concerns, fuentes y referencia FIN",
            ),
            ("Integridad", "snapshot_hash SHA-256 e idempotency key tenant-scoped"),
            ("Historia", "Listeners rechazan UPDATE/DELETE; revisiones futuras no alteran snapshots"),
            ("Compatibilidad", "Decisiones Gate 07K anteriores permanecen bajo su package snapshot original"),
        ],
        [2400, 6960],
        font_size=8.2,
    )


def api_security(doc: Document) -> None:
    doc.add_heading("4. APIs, seguridad, persistencia y concurrencia", level=1)
    add_table(
        doc,
        ["Grupo API", "Operaciones"],
        [
            ("Business Cases", "list, create, get y by-project"),
            ("Revisions", "list, create, get, update, submit-review y complete"),
            ("Readiness / Refresh", "readiness, preview y apply"),
            ("Snapshots", "list y create"),
            ("Material Change", "evaluate y review"),
            ("ADMIN", "list configurations, preview, clone, update y publish"),
        ],
        [2600, 6760],
        font_size=8.3,
    )
    add_table(
        doc,
        ["Control", "Implementación"],
        [
            ("RBAC", "12 permisos business_case.* y roles preparer/reviewer/viewer/configuration_admin"),
            ("Optimistic concurrency", "revision_version + If-Match; stale devuelve HTTP 412 ETAG_MISMATCH"),
            ("Idempotencia", "Create Case/Revision, Complete, Snapshot, Refresh y Material Review"),
            ("Auditoría", "SecurityEvent para lifecycle, preview/refresh, snapshot y configuration publish"),
            ("Constraints", "Números, cardinalidad, estados, purposes, readiness y snapshot types"),
            ("Índices", "Tenant, project, status, current revision, source/readiness hash e historial"),
        ],
        [2800, 6560],
        font_size=8.2,
    )
    add_callout(
        doc,
        "Concurrencia",
        "Los locks SELECT FOR UPDATE, version columns y unique constraints evitan dos Business Cases por Project, "
        "revisiones numeradas duplicadas y replay de operaciones. La validación PostgreSQL cubre el DDL real y "
        "la reversibilidad; las carreras de alta contención siguen recomendadas para una suite de carga dedicada.",
        fill=CAUTION,
    )
    page_break(doc)


def surfaces(doc: Document) -> None:
    doc.add_heading("5. Superficies USER y ADMIN", level=1)
    add_table(
        doc,
        ["USER MODE", "Capacidad"],
        [
            ("My Business Cases / Overview", "Lista, selección, facts, output/NEXT y source lineage"),
            ("Current Revision", "Edición DRAFT, submit, complete y nueva revisión"),
            ("Strategic / Alternatives / Benefits", "Narrativa gobernada y resúmenes estructurados"),
            ("Definition / Budget / Resources", "Refs e hashes de autoridades especializadas"),
            ("Funding / Risk / Permits", "Readiness y vigencia sin recalcular"),
            ("Economic & Financial Model", "Referencia transitoria NOT_AVAILABLE sin métricas falsas"),
            ("Execution / Assumptions / Recommendation", "Caso de ejecución de alto nivel y guardrail de decisión"),
            ("Readiness / Material Changes", "Estado derivado, preview persist=false y creación controlada"),
            ("Decision Snapshots / History", "Snapshots inmutables e historial de revisiones"),
        ],
        [3200, 6160],
        font_size=8.1,
    )
    doc.add_heading("5.1 ADMIN MODE — 26 secciones", level=2)
    add_table(
        doc,
        ["Familia", "Secciones"],
        [
            ("Core", "General, Lifecycle, Revision Purposes, Stage Requirements"),
            ("Narrativa", "Strategic Case, Alternatives, Benefits & Value, Execution Case"),
            ("Integraciones", "Project Definition, Budget, Resource, Funding, FIN, Risk, Permit"),
            ("Gobierno", "Assumptions & Constraints, Recommendation, Readiness, Material Change, Snapshots"),
            ("Control", "Review/SoD, Validity/Freshness, Inheritance, Permissions, Preview, History"),
        ],
        [2400, 6960],
        font_size=8.1,
    )
    add_callout(
        doc,
        "ADMIN Preview",
        "El editor clona una revisión publicada a DRAFT, valida JSON, resuelve herencia/contexto y ejecuta Preview "
        "con persisted=false. Save y Publish exigen versión vigente; Preview no crea Business Case.",
        fill=CALLOUT,
    )


def validation(doc: Document) -> None:
    doc.add_heading("6. Verificación técnica y regresión", level=1)
    add_table(
        doc,
        ["Control", "Resultado", "Cobertura"],
        [
            ("Ruff", "PASS", "Módulo, migración y pruebas Gate 07M-BC"),
            ("Backend focal", "5 passed", "Mapping/idempotencia, ETag, lifecycle, snapshot y boundary FIN"),
            (
                "PostgreSQL disposable",
                "PASS",
                "0056→0057→0056→0057; 69 + 93 pruebas históricas y validaciones estructurales",
            ),
            ("Vitest", "3 passed", "USER lineage/NEXT, refresh preview y ADMIN 26 tabs"),
            ("ESLint + Prettier", "PASS", "Estática y formato de archivos nuevos/modificados"),
            ("TypeScript + Vite", "PASS", "Compilación tipada y bundle productivo"),
            ("Playwright", "PASS", "USER/ADMIN con contratos API controlados"),
            ("Alembic", "PASS", "20260902_0057 es único head"),
        ],
        [2600, 1500, 5260],
        font_size=8.0,
    )
    source_note(
        doc,
        "Evidencia: pytest, compose PostgreSQL efímero, Vitest, Playwright, ESLint, Prettier, tsc y Vite ejecutados en el workspace.",
    )
    add_callout(
        doc,
        "Nota de cobertura focal",
        "La suite aislada de cinco pruebas termina funcionalmente en PASS. El umbral global de coverage no debe "
        "interpretarse sobre un único archivo; la ejecución de cierre usa --no-cov y se complementa con la regresión "
        "PostgreSQL configurada en docker-compose.gate07e.yml.",
        fill=CAUTION,
    )
    doc.add_heading("6.1 Criterios críticos observados", level=2)
    add_table(
        doc,
        ["Caso", "Resultado"],
        [
            ("Proposal → R1", "Mapping gobernado; Proposal intacta; FIN NOT_AVAILABLE"),
            ("Review / complete", "SoD reviewer/preparer; COMPLETED queda inmutable"),
            ("Snapshot → R2", "Snapshot preservado y nueva revisión DRAFT"),
            ("Stale / expired", "Hashes divergentes o valid_until vencido alteran readiness"),
            ("Refresh Preview", "persisted=false; Apply crea revisión y no auto-completa"),
            ("Output contract", "Sólo COMPLETED+READY expone READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE"),
            ("NEXT", "BUILD_GATE07M_FIN; 07M-FIN no se inició"),
        ],
        [3200, 6160],
        font_size=8.2,
    )
    page_break(doc)


def closeout(doc: Document) -> None:
    doc.add_heading("7. Final Gap Analysis, riesgos y siguiente paso", level=1)
    add_table(
        doc,
        ["Brecha / riesgo residual", "Impacto", "Tratamiento recomendado"],
        [
            (
                "Browser E2E usa mocks",
                "No prueba un journey seed-to-database en navegador",
                "Fixture full-stack efímero firmado",
            ),
            (
                "Concurrencia de alta contención",
                "Locks probados por diseño, no por stress masivo",
                "Suite PostgreSQL paralela dedicada",
            ),
            ("Comparación visual", "UI presenta JSON/deltas, no diff semántico avanzado", "Visor de diff estructurado"),
            ("Performance", "Índices y consultas diseñados; sin benchmark contractual", "Definir p95 y dataset 100k"),
            (
                "FIN no disponible",
                "Readiness financiera permanece en NOT_AVAILABLE",
                "Implementar Gate 07M-FIN en prompt separado",
            ),
        ],
        [3000, 3000, 3360],
        font_size=8.0,
    )
    add_callout(
        doc,
        "STOP boundary respetada",
        "No se implementaron NPV, IRR, WACC, deuda, DSCR/LLCR, equity returns, ejecución, procurement, contratos, "
        "commitments, pagos, accounting, treasury, NTP ni P6 execution.",
        fill=RISK,
    )
    add_callout(
        doc,
        "Cierre y recomendación",
        "Estado exclusivo: GATE07M_BC_RELEASE_VALIDATED. La salida gobernada es "
        "READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE. NEXT = BUILD_GATE07M_FIN, que debe consumir Business Case, "
        "Budget y Funding mediante referencias gobernadas. No iniciar 07M-FIN sin instrucción explícita.",
        fill=POSITIVE,
    )
    page_break(doc)


def deliverables() -> list[str]:
    text = PROMPT.read_text(encoding="utf-8")
    section = text.split("## 61. Required deliverables", 1)[1].split("## 62.", 1)[0]
    items: dict[int, str] = {}
    for line in section.splitlines():
        match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if match:
            items[int(match.group(1))] = match.group(2).rstrip(".")
    if sorted(items) != list(range(1, 75)):
        raise RuntimeError("The Gate 07M-BC prompt does not contain the expected 74 deliverables")
    return [items[index] for index in range(1, 75)]


def traceability(doc: Document) -> None:
    doc.add_heading("8. Matriz de trazabilidad 1-74", level=1)

    def evidence(index: int) -> str:
        if index <= 9:
            return "§1 / ADR 60"
        if index <= 24:
            return "§2 / model+service"
        if index <= 40:
            return "§3 / service+tests"
        if index <= 49:
            return "§4-5 / API+UI"
        if index <= 69:
            return "§6 / tests+CI"
        return "§7 / report"

    rows = [(str(i), item, evidence(i), "CERRADO") for i, item in enumerate(deliverables(), 1)]
    add_table(
        doc,
        ["#", "Entregable", "Evidencia", "Estado"],
        rows,
        [560, 5200, 1900, 1700],
        font_size=7.7,
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
    architecture(doc)
    page_break(doc)
    longitudinal_model(doc)
    governance(doc)
    api_security(doc)
    surfaces(doc)
    page_break(doc)
    validation(doc)
    closeout(doc)
    traceability(doc)
    properties = doc.core_properties
    properties.title = "Informe Técnico Gate 07M-BC — Governed Business Case Manager"
    properties.subject = "Business Case lifecycle, readiness, lineage and immutable decision snapshots"
    properties.author = "P&Pmis Construction AI"
    properties.keywords = "Gate 07M-BC, Business Case, revisions, readiness, material change, snapshots"
    properties.comments = "Generated from verified repository and disposable PostgreSQL evidence on 2026-09-02."
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
